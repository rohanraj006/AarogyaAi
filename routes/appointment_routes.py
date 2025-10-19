# routes/appointment_routes.py

from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import List
from bson import ObjectId
from datetime import datetime
from pymongo.cursor import Cursor

from models.schemas import User, DoctorInfo, AppointmentRequestModel, AppointmentConfirmBody
from security import get_current_user
from database import user_collection, appointments_collection

router = APIRouter()

# --- 1. Public Doctor Directory ---
@router.get("/doctors/public", response_model=List[DoctorInfo], tags=["Appointments"])
async def list_public_doctors():
    """Lists all doctors who are both Authorized AND have explicitly set their profile to public."""
    # Find doctors where user_type is "doctor", is_public is True, AND is_authorized is True
    doctors_cursor: Cursor = user_collection.find({
        "user_type": "doctor", 
        "is_public": True,
        "is_authorized": True
    })
    
    # Return DoctorInfo with all new status fields
    return [
        DoctorInfo(
            email=doc["email"], 
            aarogya_id=doc["aarogya_id"],
            is_public=doc.get("is_public", False), 
            is_authorized=doc.get("is_authorized", False)
        ) 
        for doc in doctors_cursor
    ]

# --- 2. Connected Doctors List ---
@router.get("/doctors/connected", response_model=List[DoctorInfo], tags=["Appointments"])
async def get_connected_doctors(current_user: User = Depends(get_current_user)):
    """Lists all doctors the logged-in patient is currently connected to."""
    if current_user.user_type != "patient":
        raise HTTPException(status_code=403, detail="Only patients can view their connected doctors list.")
    
    if not current_user.doctor_list:
        return []

    # Query the user collection for doctor details where email is in the patient's doctor_list
    connected_doctors_cursor: Cursor = user_collection.find({"email": {"$in": current_user.doctor_list}})
    
    # Return DoctorInfo with all new status fields
    return [
        DoctorInfo(
            email=doc["email"], 
            aarogya_id=doc["aarogya_id"],
            is_public=doc.get("is_public", False),
            is_authorized=doc.get("is_authorized", False)
        ) 
        for doc in connected_doctors_cursor
    ]

# --- 3. Request Appointment Endpoint (Patient) ---
@router.post("/request", status_code=status.HTTP_201_CREATED, tags=["Appointments"])
async def request_appointment(
    doctor_aarogya_id: str = Body(...),
    reason: str = Body(...),
    current_user: User = Depends(get_current_user)
):
    """Allows a patient to request an appointment with a doctor."""
    if current_user.user_type != "patient":
        raise HTTPException(status_code=403, detail="Only patients can request appointments.")

    doctor = user_collection.find_one({"aarogya_id": doctor_aarogya_id, "user_type": "doctor"})
    if not doctor:
        raise HTTPException(status_code=404, detail=f"Doctor not found with AarogyaID: {doctor_aarogya_id}")
    
    # NEW SECURITY CHECK: Patient can only request an appointment from an authorized doctor
    if doctor.get("is_authorized") != True:
         raise HTTPException(status_code=403, detail="The selected doctor is not yet authorized by the platform owner.")


    # Prevent duplicate pending requests
    existing_request = appointments_collection.find_one({
        "patient_email": current_user.email,
        "doctor_email": doctor["email"],
        "status": "pending"
    })
    if existing_request:
        raise HTTPException(status_code=400, detail="You already have a pending appointment request with this doctor.")

    appointment_data = AppointmentRequestModel(
        patient_email=current_user.email,
        doctor_email=doctor["email"],
        reason=reason
    )
    
    appointments_collection.insert_one(appointment_data.dict(by_alias=True))
    
    return {"message": "Appointment request sent successfully.", "doctor_email": doctor["email"]}


# --- 4. Doctor's Pending Queue ---
@router.get("/pending", response_model=List[AppointmentRequestModel], tags=["Appointments"])
async def get_pending_appointments(current_user: User = Depends(get_current_user)):
    """Allows a doctor to view all their pending appointment requests."""
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can view their appointment queue.")
    
    # NEW SECURITY CHECK: Unauthorized doctors cannot access their queue
    if current_user.is_authorized != True:
        raise HTTPException(status_code=403, detail="You must be authorized by the platform owner to access your appointment queue.")
    
    requests_cursor = appointments_collection.find({
        "doctor_email": current_user.email,
        "status": "pending"
    }).sort("timestamp", 1) # Oldest requests first
    
    # FIX: Convert MongoDB's ObjectId to a string before Pydantic validation
    return [
        AppointmentRequestModel(**{**req, "_id": str(req["_id"])}) 
        for req in requests_cursor
    ]


# --- 5. Confirm Appointment Endpoint (Doctor) ---
@router.post("/confirm", tags=["Appointments"])
async def confirm_appointment(
    body: AppointmentConfirmBody,
    current_user: User = Depends(get_current_user)
):
    """Allows a doctor to confirm an appointment, set a time, and generate a meeting link."""
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can confirm appointments.")
        
    # NEW SECURITY CHECK: Block unauthorized doctors from confirming appointments
    if current_user.is_authorized != True:
        raise HTTPException(status_code=403, detail="You must be authorized by the platform owner to confirm appointments.")
    
    request_obj_id = ObjectId(body.request_id)
    
    # 1. Fetch and validate the pending request
    request = appointments_collection.find_one({
        "_id": request_obj_id,
        "doctor_email": current_user.email,
        "status": "pending"
    })

    if not request:
        raise HTTPException(status_code=404, detail="Pending appointment request not found or already processed.")
    
    patient_email = request["patient_email"]

    # Simulated Meeting Link (Placeholder for actual Google Meet API call)
    meeting_link = f"https://meet.google.com/aarogya-{body.request_id}" 
    
    # 3. Update the request status and set meeting details
    appointments_collection.update_one(
        {"_id": request_obj_id},
        {"$set": {
            "status": "confirmed",
            "appointment_time": body.appointment_time,
            "meeting_link": meeting_link
        }}
    )

    return {
        "message": f"Appointment confirmed for {patient_email}.",
        "appointment_time": body.appointment_time.isoformat(),
        "meeting_link": meeting_link
    }