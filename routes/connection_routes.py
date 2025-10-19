# routes/connection_routes.py

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
# UPDATED IMPORT: Use new session dependency
from security import get_current_authenticated_user 
from database import user_collection, connection_requests_collection # Motor collections
# UPDATED IMPORT: Use rich schema name
from models.schemas import User, ConnectionRequestModel

router = APIRouter()

@router.post("/request/{patient_aarogya_id}", status_code=status.HTTP_201_CREATED)
async def request_connection(
    patient_aarogya_id: str,
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Allows a logged-in DOCTOR to send a connection request to a PATIENT.
    """
    if current_user.user_type != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can send connection requests."
        )
    
    # Check if the current doctor is authorized
    if not current_user.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be authorized by the platform owner to initiate patient connections."
        )

    # Use await for Motor
    patient = await user_collection.find_one({"aarogya_id": patient_aarogya_id})
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No patient found with AarogyaID: {patient_aarogya_id}"
        )
    
    # Ensure target is a patient
    if patient.get("user_type") != "patient":
         raise HTTPException(status_code=400, detail="Target AarogyaID must belong to a patient.")


    # Use await for Motor
    existing_request = await connection_requests_collection.find_one({
        "doctor_email": current_user.email,
        "patient_email": patient["email"],
        "$or": [{"status": "pending"}, {"status": "accepted"}] # Check both pending and accepted
    })
    if existing_request:
        status_detail = existing_request["status"]
        if status_detail == "accepted":
            detail = "You are already connected with this patient."
        else:
            detail = "A pending connection request already exists."

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )

    # Use the new rich schema name and model_dump
    connection_data = ConnectionRequestModel(
        doctor_email=current_user.email,
        patient_email=patient["email"]
    )
    
    # Use await for Motor
    await connection_requests_collection.insert_one(connection_data.model_dump())
    
    return {"message": "Connection request sent successfully."}


@router.get("/requests/pending", response_model=List[ConnectionRequestModel])
async def get_pending_requests(current_user: User = Depends(get_current_authenticated_user)):
    """
    Allows a logged-in PATIENT to see a list of their pending connection requests.
    """
    if current_user.user_type != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients can view connection requests."
        )

    # Use await for Motor and to_list
    requests_cursor = connection_requests_collection.find({
        "patient_email": current_user.email,
        "status": "pending"
    }).sort("timestamp", -1)
    
    requests_list = await requests_cursor.to_list(length=100)

    return [
        ConnectionRequestModel(**{**req, "_id": str(req["_id"])}) 
        for req in requests_list
    ]

@router.get("/requests/accept/{request_id}", status_code=status.HTTP_200_OK)
async def accept_connection_request(
    request_id: str,
    current_user: User = Depends(get_current_authenticated_user)
):
    if current_user.user_type != "patient":
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail="Only patients can accept request."
        )
    
    try:
        request_obj_id = ObjectId(request_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request_id format.")

    # Use await for Motor
    request = await connection_requests_collection.find_one({
        "_id":request_obj_id,
        "patient_email": current_user.email,
        "status":"pending"
    })

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending request not found"
        )
    
    # Use await for Motor
    await connection_requests_collection.update_one(
        {"_id": request_obj_id},
        {"$set": {"status": "accepted"}}
    )
    
    doctor_email = request["doctor_email"]
    patient_email = current_user.email
    
    # Use await for Motor
    await user_collection.update_one(
        {"email": doctor_email},
        {"$addToSet": {"patient_list": patient_email}}
    )
    
    # Use await for Motor
    await user_collection.update_one(
        {"email": patient_email},
        {"$addToSet": {"doctor_list": doctor_email}}
    )
    
    return {"message": "Connection request accepted successfully."}


@router.post("/requests/reject/{request_id}", status_code=status.HTTP_200_OK)
async def reject_connection_request(
    request_id: str,
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Allows a logged-in PATIENT to reject a connection request from a DOCTOR.
    """
    if current_user.user_type != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients can reject requests."
        )
    
    try:
        request_obj_id = ObjectId(request_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request_id format.")
    
    # Use await for Motor
    request = await connection_requests_collection.find_one({
        "_id": request_obj_id,
        "patient_email": current_user.email,
        "status": "pending"
    })

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending request not found."
        )

    # Simply update the status to "rejected"
    # Use await for Motor
    await connection_requests_collection.update_one(
        {"_id": request_obj_id},
        {"$set": {"status": "rejected"}}
    )
    
    return {"message": "Connection request rejected."}