# routes/connection_routes.py

from bson import ObjectId
from fastapi import APIRouter, Body, Depends, HTTPException, status
from typing import List
from datetime import datetime, timedelta
from bson import ObjectId
from fastapi.responses import JSONResponse
# UPDATED IMPORT: Use new session dependency
from security import get_current_authenticated_user 
from database import user_collection, connection_requests_collection, instant_meetings_collection
# UPDATED IMPORT: Use rich schema name
from models.schemas import User, ConnectionRequestModel
from ai_core.chatbot_service import MedicalChatbot
from app.services.google_service import create_google_meet_link

router = APIRouter()
chatbot = MedicalChatbot()

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



@router.post("/instant/request", tags=["Instant Care"])
async def request_instant_consultation(
    request_data: dict = Body(...), 
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Handles the Blind Match. Finds an available doctor and 'locks' them.
    """
    # 1. Determine Specialization
    target_specialty = ""
    if request_data['type'] == 'specialty':
        target_specialty = request_data['value']
    elif request_data['type'] == 'symptoms':
        # Use AI to find the right doctor
        target_specialty = await chatbot.predict_specialty_from_symptoms(request_data['value'])
    
    print(f"Searching for: {target_specialty}") # Debug log

    # 2. Find an AVAILABLE Doctor
    # Rules: User type is doctor, Status is available, Is Public, Matches Specialty
    # Optimization: Sort by last_active or random to distribute load (using find_one for MVP)
    matched_doctor = await user_collection.find_one({
        "user_type": "doctor",
        "availability_status": "available",
        "is_public": True,
        "is_authorized":True,
        "specialization": {"$regex": target_specialty.split()[0], "$options": "i"} 
    })

    if not matched_doctor:
        # Fallback: If specialized doctor not found, try General Physician
        if target_specialty != "General Physician":
            matched_doctor = await user_collection.find_one({
                "user_type": "doctor",
                "availability_status": "available",
                "is_public": True,
                "specialization": {"$regex": "General", "$options": "i"}
            })
    
    if not matched_doctor:
        return JSONResponse(
            status_code=404, 
            content={"detail": f"No {target_specialty} is currently online. Please try again in a moment."}
        )

    # 3. LOCK the Doctor (Set them to 'busy' so no one else catches them)
    # This acts as a semaphore/mutex
    await user_collection.update_one(
        {"_id": matched_doctor["_id"]},
        {"$set": {"availability_status": "busy"}} 
    )

    # 4. Create the Connection Request
    new_request = {
        "patient_id": str(current_user.id),
        "doctor_id": str(matched_doctor["_id"]),
        "patient_name": f"{current_user.name.first} {current_user.name.last}",
        "doctor_name": f"{matched_doctor['name']['first']} {matched_doctor['name']['last']}",
        "specialization": matched_doctor.get('specialization', 'Doctor'),
        "symptoms": request_data.get('value') if request_data['type'] == 'symptoms' else "Direct Request",
        "status": "pending", # The doctor sees this
        "created_at": datetime.utcnow(),
        "type": "instant",   # Flag to distinguish from normal appointments
        "expires_at": datetime.utcnow() + timedelta(seconds=60) # 60s timeout
    }
    
    result = await instant_meetings_collection.insert_one(new_request)

    return {
        "message": "Doctor found! Waiting for acceptance...",
        "request_id": str(result.inserted_id),
        "doctor_name": f"Dr. {matched_doctor['name']['last']}",
        "specialty": target_specialty
    }

# --- INSTANT CARE LIFECYCLE ROUTES ---

@router.get("/instant/incoming", tags=["Instant Care"])
async def check_incoming_instant_requests(current_user: User = Depends(get_current_authenticated_user)):
    """
    DOCTOR POLLING: Checks if there are any pending instant requests for this doctor.
    """
    if current_user.user_type != "doctor":
        return []

    # Find pending requests for this doctor that haven't expired
    # (Optional: Add logic to filter out expired requests based on time)
    request = await instant_meetings_collection.find_one({
        "doctor_id": str(current_user.id),
        "status": "pending"
    })

    if not request:
        return {"has_request": False}

    return {
        "has_request": True,
        "request_id": str(request["_id"]),
        "patient_name": request["patient_name"],
        "symptoms": request["symptoms"],
        "severity": "High" # Placeholder or derived from AI
    }


@router.get("/instant/status/{request_id}", tags=["Instant Care"])
async def check_instant_request_status(
    request_id: str, 
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    PATIENT POLLING: Checks if their request has been accepted.
    """
    try:
        req = await instant_meetings_collection.find_one({"_id": ObjectId(request_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID")

    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    return {
        "status": req["status"],
        "meet_link": req.get("meet_link"),
        "doctor_name": req.get("doctor_name")
    }


@router.post("/instant/accept/{request_id}", tags=["Instant Care"])
async def accept_instant_request(
    request_id: str, 
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    DOCTOR ACTION: Accepts the request and generates a Google Meet link.
    """
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can accept.")

    # 1. Verify Request
    req = await instant_meetings_collection.find_one({
        "_id": ObjectId(request_id), 
        "doctor_id": str(current_user.id),
        "status": "pending"
    })
    
    if not req:
        raise HTTPException(status_code=404, detail="Request not found or expired.")

    # 2. Generate Google Meet Link
    meet_link = create_google_meet_link(
        summary=f"Instant Consult: Dr. {current_user.name.last} & {req['patient_name']}",
        start_time=datetime.utcnow(),
        attendee_emails=[current_user.email] # Add patient email if available in user doc
    )

    # 3. Update Database
    await instant_meetings_collection.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": {
            "status": "accepted", 
            "meet_link": meet_link,
            "accepted_at": datetime.utcnow()
        }}
    )
    
    # 4. Set Doctor to 'In Meeting' (Busy)
    await user_collection.update_one(
        {"_id": current_user.id},
        {"$set": {"availability_status": "busy"}}
    )

    return {"message": "Accepted", "meet_link": meet_link}


@router.post("/instant/reject/{request_id}", tags=["Instant Care"])
async def reject_instant_request(
    request_id: str, 
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    DOCTOR ACTION: Rejects the request. 
    (Future: This could trigger re-routing to another doctor)
    """
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can reject.")

    await instant_meetings_collection.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": {"status": "rejected"}}
    )

    # Set Doctor back to Available since they didn't take it
    await user_collection.update_one(
        {"_id": current_user.id},
        {"$set": {"availability_status": "available"}}
    )

    return {"message": "Rejected"}

