# routes/appointment_routes.py

from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import List, Optional
from bson import ObjectId
from datetime import datetime
from pymongo.cursor import Cursor
from ai_core.rag_engine import predict_symptom_severity
from models.schemas import User, DoctorInfo, AppointmentRequestModel, AppointmentConfirmBody
from security import get_current_authenticated_user # UPDATED IMPORT
from database import user_collection, appointments_collection

router = APIRouter()

# --- 1. Public Doctor Directory ---
@router.get("/doctors/public", response_model=List[DoctorInfo], tags=["Appointments"])
async def list_public_doctors():
    """Lists all doctors who are both Authorized AND have explicitly set their profile to public."""
    
    doctors_cursor: Cursor = user_collection.find({
        "user_type": "doctor", 
        "is_public": True,
        "is_authorized": True
    })
    
    # Convert cursor to list asynchronously
    doctors_list = await doctors_cursor.to_list(length=100)
    
    # Return DoctorInfo with all new status fields
    return [
        DoctorInfo(
            email=doc["email"], 
            aarogya_id=doc["aarogya_id"],
            is_public=doc.get("is_public", False), 
            is_authorized=doc.get("is_authorized", False)
        ) 
        for doc in doctors_list
    ]

# --- 2. Connected Doctors List ---
# UPDATED DEPENDENCY
@router.get("/doctors/connected", response_model=List[DoctorInfo], tags=["Appointments"])
async def get_connected_doctors(current_user: User = Depends(get_current_authenticated_user)):
    """Lists all doctors the logged-in patient is currently connected to."""
    if current_user.user_type != "patient":
        raise HTTPException(status_code=403, detail="Only patients can view their connected doctors list.")
    
    if not current_user.doctor_list:
        return []

    # Query the user collection for doctor details where email is in the patient's doctor_list
    connected_doctors_cursor: Cursor = user_collection.find({"email": {"$in": current_user.doctor_list}})
    
    # Convert cursor to list asynchronously
    connected_doctors_list = await connected_doctors_cursor.to_list(length=len(current_user.doctor_list))
    
    # Return DoctorInfo with all new status fields
    return [
        DoctorInfo(
            email=doc["email"], 
            aarogya_id=doc["aarogya_id"],
            is_public=doc.get("is_public", False),
            is_authorized=doc.get("is_authorized", False)
        ) 
        for doc in connected_doctors_list
    ]

# --- 3. Request Appointment Endpoint (Patient) ---
# UPDATED DEPENDENCY
@router.post("/request", status_code=status.HTTP_201_CREATED, tags=["Appointments"])
async def request_appointment(
    # Updated to accept rich fields
    doctor_aarogya_id: str = Body(..., embed=True),
    reason: str = Body(..., embed=True),
    patient_notes: Optional[str] = Body(None, embed=True), # NEW FIELD: Patient's symptoms
    appointment_time: Optional[datetime] = Body(None, embed=True), # NEW FIELD: Preferred time/date
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Allows a patient to request an appointment with a doctor. Now includes 
    AI-driven severity prediction (triage).
    """
    if current_user.user_type != "patient":
        raise HTTPException(status_code=403, detail="Only patients can request appointments.")

    doctor = await user_collection.find_one({"aarogya_id": doctor_aarogya_id, "user_type": "doctor"})
    if not doctor:
        raise HTTPException(status_code=404, detail=f"Doctor not found with AarogyaID: {doctor_aarogya_id}")
    
    if doctor.get("is_authorized") != True:
         raise HTTPException(status_code=403, detail="The selected doctor is not yet authorized by the platform owner.")


    # --- Triage Logic ---
    if not patient_notes or not patient_notes.strip():
        # Fallback to general severity if no notes, or raise error if essential
        # Raising error is better for data quality
        raise HTTPException(status_code=400, detail="Patient notes/symptoms are required for the AI triage system.")

    predicted_severity = await predict_symptom_severity(
        patient_email=current_user.email,
        reason=reason,
        patient_notes=patient_notes
    )
    # --- End Triage Logic ---

    # Prevent duplicate pending requests
    existing_request = await appointments_collection.find_one({
        "patient_email": current_user.email,
        "doctor_email": doctor["email"],
        "status": "pending"
    })
    if existing_request:
        raise HTTPException(status_code=400, detail="You already have a pending appointment request with this doctor.")

    # Populate the full AppointmentRequestModel with new fields
    appointment_data = AppointmentRequestModel(
        patient_email=current_user.email,
        doctor_email=doctor["email"],
        reason=reason,
        patient_notes=patient_notes,
        status="pending",
        appointment_time=appointment_time,
        predicted_severity=predicted_severity # NEW FIELD
    )
    
    await appointments_collection.insert_one(appointment_data.model_dump(by_alias=True))
    
    return {
        "message": "Appointment request sent successfully.", 
        "doctor_email": doctor["email"],
        "predicted_severity": predicted_severity
    }

# --- 4. Doctor's Pending Queue ---
# UPDATED DEPENDENCY
@router.get("/pending", response_model=List[AppointmentRequestModel], tags=["Appointments"])
async def get_pending_appointments(current_user: User = Depends(get_current_authenticated_user)):
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
    
    requests_list = await requests_cursor.to_list(length=100) # Convert cursor to list asynchronously

    # FIX: Convert MongoDB's ObjectId to a string before Pydantic validation
    return [
        AppointmentRequestModel(**{**req, "_id": str(req["_id"])}) 
        for req in requests_list
    ]


# --- 5. Confirm Appointment Endpoint (Doctor) ---
# UPDATED DEPENDENCY
@router.post("/confirm", tags=["Appointments"])
async def confirm_appointment(
    body: AppointmentConfirmBody,
    current_user: User = Depends(get_current_authenticated_user)
):
    """Allows a doctor to confirm an appointment, set a time, and generate a meeting link."""
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can confirm appointments.")
        
    # NEW SECURITY CHECK: Block unauthorized doctors from confirming appointments
    if current_user.is_authorized != True:
        raise HTTPException(status_code=403, detail="You must be authorized by the platform owner to confirm appointments.")
    
    try:
        request_obj_id = ObjectId(body.request_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request_id format.")

    
    # 1. Fetch and validate the pending request
    request = await appointments_collection.find_one({ # Use await for Motor
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
    await appointments_collection.update_one( # Use await for Motor
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