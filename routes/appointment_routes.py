# routes/appointment_routes.py

from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
from typing import List, Optional
from bson import ObjectId
from datetime import datetime
from pymongo.cursor import Cursor
import tempfile
import os
import anyio
import random
import string
from fastapi.concurrency import run_in_threadpool

# Imports
from models.schemas import User, DoctorInfo, AppointmentRequestModel, AppointmentConfirmBody
from security import get_current_authenticated_user
from database import user_collection, appointments_collection
from ai_core.chatbot_service import MedicalChatbot
from ai_core.helpers import fetch_patient_context
from app.services.google_service import create_google_meet_link

router = APIRouter()
chatbot = MedicalChatbot()

# Initialize Whisper
try:
    from faster_whisper import WhisperModel
    import torch
    WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "tiny")
    WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
    WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16" if WHISPER_DEVICE == "cuda" else "int8")
    whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
except ImportError:
    whisper_model = None

# ... (Keep list_public_doctors, get_connected_doctors, transcribe_audio, request_appointment, reject_appointment as they were) ...
# I will output the modified Confirm, Activate, and List endpoints below.

# --- 1. Public Doctor Directory ---
@router.get("/doctors/public", response_model=List[DoctorInfo], tags=["Appointments"])
async def list_public_doctors():
    doctors_cursor: Cursor = user_collection.find({
        "user_type": "doctor", 
        "is_public": True,
        "is_authorized": True
    })
    doctors_list = await doctors_cursor.to_list(length=100)
    return [
        DoctorInfo(
            email=doc["email"], 
            aarogya_id=doc["aarogya_id"],
            is_public=doc.get("is_public", False), 
            is_authorized=doc.get("is_authorized", False)
        ) for doc in doctors_list
    ]

# --- 2. Connected Doctors List ---
@router.get("/doctors/connected", response_model=List[DoctorInfo], tags=["Appointments"])
async def get_connected_doctors(current_user: User = Depends(get_current_authenticated_user)):
    if current_user.user_type != "patient":
        raise HTTPException(status_code=403, detail="Only patients can view their connected doctors list.")
    
    if not current_user.doctor_list:
        return []

    connected_doctors_cursor: Cursor = user_collection.find({"email": {"$in": current_user.doctor_list}})
    connected_doctors_list = await connected_doctors_cursor.to_list(length=len(current_user.doctor_list))
    
    return [
        DoctorInfo(
            email=doc["email"], 
            aarogya_id=doc["aarogya_id"],
            is_public=doc.get("is_public", False),
            is_authorized=doc.get("is_authorized", False)
        ) for doc in connected_doctors_list
    ]

# --- 3. Transcribe Audio ---
@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    if not whisper_model:
        return {"transcription": "Transcription service unavailable."}
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            content = await file.read()
            await anyio.to_thread.run_sync(tmp.write, content)
            tmp_path = tmp.name

        segments, _ = await run_in_threadpool(whisper_model.transcribe, tmp_path)
        text = " ".join([s.text for s in segments])
        
        os.remove(tmp_path)
        return {"transcription": text}
    except Exception as e:
        return {"error": str(e)}

# --- 4. Request Appointment (Patient) ---
@router.post("/request", status_code=status.HTTP_201_CREATED, tags=["Appointments"])
async def request_appointment(
    doctor_aarogya_id: str = Form(...),
    reason: str = Form(...),
    patient_notes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_authenticated_user)
):
    if current_user.user_type != "patient":
        raise HTTPException(status_code=403, detail="Only patients can request appointments.")

    doctor = await user_collection.find_one({"aarogya_id": doctor_aarogya_id, "user_type": "doctor"})
    if not doctor:
        raise HTTPException(status_code=404, detail=f"Doctor not found.")
    
    if doctor.get("is_authorized") != True:
         raise HTTPException(status_code=403, detail="Doctor not authorized.")

    if doctor["email"] not in current_user.doctor_list:
        raise HTTPException(status_code=403, detail="Not connected to this doctor.")

    if not patient_notes or not patient_notes.strip():
        raise HTTPException(status_code=400, detail="Patient notes required.")

    context_data = await fetch_patient_context(current_user.email)
    predicted_severity = await chatbot.predict_severity(
        patient_data=context_data,
        reason=reason,
        notes=patient_notes 
    )

    existing = await appointments_collection.find_one({
        "patient_email": current_user.email,
        "doctor_email": doctor["email"],
        "status": "pending"
    })
    if existing:
        raise HTTPException(status_code=400, detail="Pending request already exists.")

    appointment_data = AppointmentRequestModel(
        patient_email=current_user.email,
        doctor_email=doctor["email"],
        reason=reason,
        patient_notes=patient_notes,
        status="pending",
        predicted_severity=predicted_severity,
        is_link_active=False # Default to inactive
    )
    
    await appointments_collection.insert_one(appointment_data.model_dump(by_alias=True, exclude_none=True))
    
    return {
        "message": "Request sent.", 
        "doctor_email": doctor["email"],
        "predicted_severity": predicted_severity
    }

@router.post("/reject", tags=["Appointments"])
async def reject_appointment(
    body: dict, 
    current_user: User = Depends(get_current_authenticated_user)
):
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Unauthorized.")
        
    try:
        request_obj_id = ObjectId(body.get("request_id"))
    except:
        raise HTTPException(status_code=400, detail="Invalid ID.")

    result = await appointments_collection.update_one(
        {"_id": request_obj_id, "doctor_email": current_user.email, "status": "pending"},
        {"$set": {"status": "rejected"}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Request not found.")
    
    return {"message": "Rejected."}

@router.get("/pending", response_model=List[AppointmentRequestModel], tags=["Appointments"])
async def get_pending_appointments(current_user: User = Depends(get_current_authenticated_user)):
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Unauthorized.")
    
    cursor = appointments_collection.find({
        "doctor_email": current_user.email,
        "status": "pending"
    }).sort("timestamp", 1)
    
    results = await cursor.to_list(length=100)
    return [AppointmentRequestModel(**{**req, "_id": str(req["_id"])}) for req in results]

# --- 6. Confirm Appointment (Doctor) ---
@router.post("/confirm", tags=["Appointments"])
async def confirm_appointment(
    body: AppointmentConfirmBody,
    current_user: User = Depends(get_current_authenticated_user)
):
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Unauthorized.")
        
    try:
        request_obj_id = ObjectId(body.request_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID.")

    request = await appointments_collection.find_one({
        "_id": request_obj_id,
        "doctor_email": current_user.email,
        "status": "pending"
    })

    if not request:
        raise HTTPException(status_code=404, detail="Request not found.")
    
    # Generate Link
    meeting_link = await run_in_threadpool(
        create_google_meet_link,
        summary=f"Consultation: Dr. {current_user.name.last} with Patient",
        start_time=body.appointment_time,
        attendee_emails=[request['patient_email'], current_user.email]
    )
    
    await appointments_collection.update_one(
        {"_id": request_obj_id},
        {"$set": {
            "status": "confirmed",
            "appointment_time": body.appointment_time,
            "meeting_link": meeting_link,
            "is_link_active": False # Explicitly keep it false until activation
        }}
    )

    return {
        "message": "Appointment confirmed.",
        "appointment_time": body.appointment_time.isoformat(),
        "meeting_link": meeting_link
    }

# --- NEW: Activate Link Endpoint (Doctor Only) ---
@router.post("/activate/{request_id}", tags=["Appointments"])
async def activate_appointment_link(
    request_id: str,
    current_user: User = Depends(get_current_authenticated_user)
):
    """Allows doctor to enable the 'Join' button for the patient."""
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Unauthorized.")

    try:
        request_obj_id = ObjectId(request_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID.")

    result = await appointments_collection.update_one(
        {"_id": request_obj_id, "doctor_email": current_user.email},
        {"$set": {"is_link_active": True}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    return {"message": "Link activated for patient."}

# --- NEW: Complete Appointment Endpoint (Doctor Only) ---
@router.post("/complete/{request_id}", tags=["Appointments"])
async def complete_appointment(
    request_id: str,
    current_user: User = Depends(get_current_authenticated_user)
):
    """Marks an appointment as completed and deactivates the link."""
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Unauthorized.")

    try:
        request_obj_id = ObjectId(request_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID.")

    result = await appointments_collection.update_one(
        {"_id": request_obj_id, "doctor_email": current_user.email},
        {"$set": {
            "status": "completed",
            "is_link_active": False # Disable link access
        }}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    return {"message": "Appointment marked as completed."}

# --- 7. Get All Appointments ---
@router.get("/list", response_model=List[AppointmentRequestModel], tags=["Appointments"])
async def get_my_appointments(current_user: User = Depends(get_current_authenticated_user)):
    query = {}
    if current_user.user_type == "patient":
        query["patient_email"] = current_user.email
    elif current_user.user_type == "doctor":
        query["doctor_email"] = current_user.email
    
    cursor = appointments_collection.find(query).sort("appointment_time", -1)
    results = await cursor.to_list(length=None)
    
    # Return everything, let frontend handle filtering/display logic based on is_link_active
    return [AppointmentRequestModel(**{**req, "_id": str(req["_id"])}) for req in results]