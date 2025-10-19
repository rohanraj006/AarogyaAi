# routes/connection_routes.py

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from models.schemas import User, ConnectionRequest
from security import get_current_user
from database import user_collection, connection_requests_collection

router = APIRouter()

@router.post("/request/{patient_aarogya_id}", status_code=status.HTTP_201_CREATED)
async def request_connection(
    patient_aarogya_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Allows a logged-in DOCTOR to send a connection request to a PATIENT.
    """
    if current_user.user_type != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can send connection requests."
        )
    
    if not current_user.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be authorized by the platform owner to initiate patient connections."
        )

    patient = user_collection.find_one({"aarogya_id": patient_aarogya_id})
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No patient found with AarogyaID: {patient_aarogya_id}"
        )

    existing_request = connection_requests_collection.find_one({
        "doctor_email": current_user.email,
        "patient_email": patient["email"]
    })
    if existing_request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A connection request already exists or is already accepted."
        )

    connection_data = ConnectionRequest(
        doctor_email=current_user.email,
        patient_email=patient["email"]
    )
    
    connection_requests_collection.insert_one(connection_data.dict())
    
    return {"message": "Connection request sent successfully."}


@router.get("/requests/pending", response_model=List[ConnectionRequest])
async def get_pending_requests(current_user: User = Depends(get_current_user)):
    """
    Allows a logged-in PATIENT to see a list of their pending connection requests.
    """
    if current_user.user_type != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients can view connection requests."
        )

    requests_cursor = connection_requests_collection.find({
        "patient_email": current_user.email,
        "status": "pending"
    }).sort("timestamp", -1)

    # 1. Convert the MongoDB ObjectId to a string using the dictionary spread.
    # 2. Use the **_id** key to ensure the ObjectId is correctly overwritten 
    #    with its string representation before Pydantic validation occurs.
    return [
        ConnectionRequest(**{**req, "_id": str(req["_id"])}) 
        for req in requests_cursor
    ]

@router.get("/requests/accept/{request_id}", status_code=status.HTTP_200_OK)
async def accept_connection_request(
    request_id: str,
    current_user: User = Depends(get_current_user)
):
    if current_user.user_type != "patient":
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail="on;y patients can accept request."
        )
    
    request_obj_id = ObjectId(request_id)
    request = connection_requests_collection.find_one({
        "_id":request_obj_id,
        "patient_email": current_user.email,
        "status":"pending"
    })

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="pending request not found"
        )
    connection_requests_collection.update_one(
        {"_id": request_obj_id},
        {"$set": {"status": "accepted"}}
    )
    doctor_email = request["doctor_email"]
    patient_email = current_user.email
    user_collection.update_one(
        {"email": doctor_email},
        {"$addToSet": {"patient_list": patient_email}}
    )
    user_collection.update_one(
        {"email": patient_email},
        {"$addToSet": {"doctor_list": doctor_email}}
    )
    return {"message": "Connection request accepted successfully."}


# --- THIS IS THE NEW "REJECT" ENDPOINT ---
@router.post("/requests/reject/{request_id}", status_code=status.HTTP_200_OK)
async def reject_connection_request(
    request_id: str,
    current_user: User = Depends(get_current_user)
):
    """

    Allows a logged-in PATIENT to reject a connection request from a DOCTOR.
    """
    if current_user.user_type != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients can reject requests."
        )
    
    request_obj_id = ObjectId(request_id)
    request = connection_requests_collection.find_one({
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
    connection_requests_collection.update_one(
        {"_id": request_obj_id},
        {"$set": {"status": "rejected"}}
    )
    
    return {"message": "Connection request rejected."}