# routes/doctor_routes.py

from fastapi import APIRouter, Body, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from typing import List, Dict, Any, Optional
from pydantic import ValidationError
from bson import ObjectId
import tempfile
import os
import io
from datetime import datetime, timezone
from fastapi.concurrency import run_in_threadpool
import anyio

# ReportLab Imports
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import inch

# Core Imports
from security import get_current_authenticated_user
# FIX: Added reports_collection to imports so we can save patient-visible reports
from database import user_collection, medical_records_collection, report_contents_collection, reports_collection

# Schemas
from models.schemas import (
    User, Name, Diagnosis, Medication, ReportPDFRequest, 
    ReportContentRequest, DictationSaveBody, Prescription, MedicalRecord, Report
)

# AI Imports
from ai_core.chatbot_service import MedicalChatbot
from ai_core.parser_service import MedicalReportParser
from ai_core.helpers import fetch_patient_context

# Initialize Services
chatbot_service = MedicalChatbot()
parser_service = MedicalReportParser(chatbot_service)

# Whisper Model Setup
try:
    from faster_whisper import WhisperModel
    import torch
    WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "tiny")
    WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
    WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16" if WHISPER_DEVICE == "cuda" else "int8")
    whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
except ImportError:
    whisper_model = None

router = APIRouter()

# --- HELPER DEPENDENCY ---
async def get_current_doctor(current_user: User = Depends(get_current_authenticated_user)):
    if current_user.user_type != "doctor": 
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Only doctors can perform this action.")
    return current_user

# --- PDF GENERATION HELPER ---
def create_report_pdf(doctor_info: dict, patient_info: dict, report_content_text: str) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet() 

    styles.add(ParagraphStyle(name='CustomNormal', fontSize=10, leading=12, alignment=TA_LEFT, spaceAfter=6))
    styles.add(ParagraphStyle(name='Heading1Center', fontSize=14, leading=16, alignment=TA_CENTER, spaceAfter=20, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='Heading2Left', fontSize=12, leading=14, alignment=TA_LEFT, spaceBefore=10, spaceAfter=5, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='Small', fontSize=9, leading=10, alignment=TA_LEFT, spaceAfter=4))
    styles.add(ParagraphStyle(name='FooterStyle', fontSize=9, leading=10, alignment=TA_CENTER, spaceBefore=10, textColor=styles['Normal'].textColor))

    Story = []
    
    doctor_name = f"Dr. {doctor_info.get('name', {}).get('first', '')} {doctor_info.get('name', {}).get('last', '')}".strip() or "Dr. [Doctor Name]"
    
    Story.append(Paragraph("<font size=12><b>Medical Report</b></font>", styles['Heading1Center']))
    Story.append(Paragraph(f"<font size=10><b>{doctor_name}</b>, {doctor_info.get('specialization', 'Medical Practitioner')}</font>", styles['CustomNormal']))
    Story.append(Paragraph(f"<font size=9>Email: {doctor_info.get('email', '')}</font>", styles['Small']))
    Story.append(Spacer(1, 0.2 * inch))

    patient_name = f"{patient_info.get('name', {}).get('first', '')} {patient_info.get('name', {}).get('last', '')}".strip() or "[Patient Name]"
    patient_dob = patient_info.get('date_of_birth', 'N/A')
    patient_id_display = str(patient_info.get('aarogya_id', patient_info.get('_id', 'N/A')))

    Story.append(Paragraph("<font size=10><b>Patient Information:</b></font>", styles['Heading2Left']))
    Story.append(Paragraph(f"<font size=10><b>Name:</b> {patient_name}</font>", styles['CustomNormal']))
    Story.append(Paragraph(f"<font size=10><b>Aarogya ID:</b> {patient_id_display}</font>", styles['CustomNormal']))
    Story.append(Paragraph(f"<font size=10><b>Date of Birth:</b> {patient_dob}</font>", styles['CustomNormal']))
    Story.append(Spacer(1, 0.3 * inch))

    Story.append(Paragraph("<font size=10><b>Report Details:</b></font>", styles['Heading2Left']))
    report_content_formatted = report_content_text.replace('\n', '<br/>') if report_content_text else "No report content provided."
    Story.append(Paragraph(report_content_formatted, styles['CustomNormal']))

    Story.append(Spacer(1, 0.5 * inch))
    footer_text = f"Generated by Aarogya AI on {datetime.now().strftime('%Y-%m-%d %H:%M')} | Page <page/> of <npgs/>"
    Story.append(Paragraph(footer_text, styles['FooterStyle'])) 

    doc.build(Story)
    buffer.seek(0) 
    return buffer

# --- ROUTES ---

@router.get("/api/patients/search")
async def search_for_patient(
    current_user: User = Depends(get_current_doctor),
    aarogya_id: str = Query(..., min_length=10, max_length=15)
):
    if not current_user.is_authorized:
        raise HTTPException(status_code=403, detail="Unauthorized access.")

    patient = await user_collection.find_one({"aarogya_id": aarogya_id, "user_type":"patient"})
    if not patient:
        raise HTTPException(status_code=404, detail=f"No patient found with ID: {aarogya_id}")
    
    if patient.get("name"):
        patient_name = Name(**patient["name"]).model_dump()
    else:
        patient_name = {"first": patient["email"].split('@')[0], "last": ""}
    
    return {
        "_id": str(patient["_id"]), 
        "aarogya_id": patient["aarogya_id"],
        "email": patient["email"],
        "name": patient_name,
        "age": patient.get("age"),
        "gender": patient.get("gender"),
        "phone_number": patient.get("phone_number"),
        "blood_group": patient.get("blood_group"),
        "address": patient.get("address"),
        "emergency_contact": patient.get("emergency_contact"),
        "medical_conditions": patient.get("medical_conditions"),
        "allergies": patient.get("allergies"),
        "current_medications": patient.get("current_medications"),
        "registration_date": patient.get("registration_date")
    }

@router.get("/my-patients", response_model=List[User])
async def get_my_patients(current_user: User = Depends(get_current_doctor)):
    if not current_user.patient_list:
        return []

    patients_cursor = user_collection.find({
        "email": {"$in": current_user.patient_list},
        "user_type": "patient"
    })
    
    patient_list = await patients_cursor.to_list(length=None)
    validated_patients = []
    for patient in patient_list:
        if '_id' in patient: patient['_id'] = str(patient['_id'])
        validated_patients.append(User.model_validate(patient))
    
    return validated_patients

@router.post("/toggle_public", tags=["Doctor"])
async def doctor_toggle_public_status(
    current_user: User = Depends(get_current_doctor),
    is_public: bool = Body(..., embed=True)
):
    if not current_user.is_authorized:
        raise HTTPException(status_code=403, detail="Unauthorized.")
    
    if not is_public: await user_collection.update_one({"email": current_user.email}, {"$set": {"availability_status": "offline"}})

    await user_collection.update_one(
        {"email": current_user.email},
        {"$set": {"is_public": is_public}}
    )
    return {"message": f"Your public status has been set to {is_public}."}

# --- TRANSCRIPTION ---
@router.post("/patient/{patient_id}/transcribe", tags=["Doctor"])
async def transcribe_medical_report(
    patient_id: str,
    audio_file: UploadFile = File(...),
    current_user: User = Depends(get_current_doctor)
):
    if not whisper_model:
        raise HTTPException(status_code=503, detail="Voice transcription model not loaded.")

    if not audio_file.filename:
        raise HTTPException(status_code=400, detail="No audio file uploaded.")

    tmp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{audio_file.filename}") as tmp_file:
            file_content = await audio_file.read()
            await anyio.to_thread.run_sync(tmp_file.write, file_content)
            tmp_file_path = tmp_file.name

        segments_generator, info = await run_in_threadpool(
             whisper_model.transcribe,
             tmp_file_path,
             beam_size=5,
             task="transcribe",
        )
        transcribed_text = "".join([segment.text for segment in segments_generator])
        
        return JSONResponse({"transcription": transcribed_text.strip()})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription error: {e}")
    finally:
        if tmp_file_path and os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)

# --- SAVE PRESCRIPTION ---
@router.post("/patient/{patient_id}/prescribe", tags=["Doctor"])
async def save_prescription(
    patient_id: str,
    prescription: Prescription, 
    current_user: User = Depends(get_current_doctor)
):
    patient = await user_collection.find_one({"aarogya_id": patient_id})
    if not patient:
        try:
             patient = await user_collection.find_one({"_id": ObjectId(patient_id)})
        except:
             pass
             
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    if patient["email"] not in current_user.patient_list:
        raise HTTPException(status_code=403, detail="Not connected to this patient.")

    presc_dict = prescription.model_dump()
    
    await medical_records_collection.update_one(
        {"patient_id": patient["email"]},
        {
            "$push": {"prescriptions": presc_dict},
            "$set": {"updated_at": datetime.utcnow()}
        },
        upsert=True
    )
    
    return {"message": "Prescription saved successfully."}

@router.get("/patient/{patient_id}/reports", tags=["Doctor"])
async def get_patient_reports(
    patient_id: str,
    current_user: User = Depends(get_current_doctor)
):
    patient = await user_collection.find_one({"aarogya_id": patient_id})
    if not patient:
         try: patient = await user_collection.find_one({"_id": ObjectId(patient_id)})
         except: pass
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    record = await medical_records_collection.find_one({"patient_id": patient["email"]})
    if not record:
        return []

    reports = record.get("reports", [])
    reports.sort(key=lambda x: x.get("upload_date", ""), reverse=True)
    return reports

@router.get("/report/content/{content_id}", tags=["Doctor"])
async def get_report_content(
    content_id: str,
    current_user: User = Depends(get_current_doctor)
):
    try:
        content = await report_contents_collection.find_one({"_id": ObjectId(content_id)})
        if content:
            return {"content": content.get("content_text", "No content text found.")}
        else:
            return {"content": "Content not found."}
    except:
        raise HTTPException(status_code=400, detail="Invalid Content ID")

@router.post("/patient/{patient_id}/save-parsed-report", tags=["Doctor"])
async def save_parsed_report_data(
    patient_id: str,
    body: ReportContentRequest, 
    current_user: User = Depends(get_current_doctor)
):
    report_content_text = body.content_text
    if not report_content_text:
        raise HTTPException(status_code=400, detail="No content to parse.")

    patient = await user_collection.find_one({"aarogya_id": patient_id})
    if not patient:
        try:
             patient = await user_collection.find_one({"_id": ObjectId(patient_id)})
        except: pass

    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    context = await fetch_patient_context(patient['email'])

    # 1. Parse Data using AI
    extracted_data = await parser_service.parse_medical_report(
        report_text=report_content_text,
        patient_data=context,
        doctor_data=current_user.model_dump()
    )

    # 2. Save Report Content (The actual text)
    content_doc = {"content_text": report_content_text, "created_at": datetime.utcnow()}
    insert_result = await report_contents_collection.insert_one(content_doc)
    content_id = str(insert_result.inserted_id)

    # 3. FIX: Create Entry in 'reports' Collection (For Patient View & Download)
    report_filename = f"Consultation_Report_{datetime.utcnow().strftime('%Y-%m-%d')}.pdf"
    
    report_entry = Report(
        filename=report_filename,
        owner_email=patient['email'],
        content_id=content_id,
        report_type="AI Generated Consultation",
        description="Doctor generated consultation report."
    )
    
    # Save to reports collection (Exclude 'id' so Mongo generates one)
    await reports_collection.insert_one(report_entry.model_dump(by_alias=True, exclude={"id"}))

    # 4. Update Medical Record (For Doctor View)
    # Using the simplified structure for embedded reports
    report_ref = {
        "report_id": content_id, # Using content ID as ref
        "report_type": "AI Generated Consultation Report",
        "date": datetime.utcnow(),
        "content_id": content_id,
        "description": report_content_text[:200] + "..." 
    }

    update_push = {"reports": report_ref}
    
    # Push extracted entities (meds, diagnosis, etc.)
    for key in ["diagnoses", "medications", "allergies", "consultations", "immunizations"]:
        if extracted_data.get(key):
            db_key = "current_medications" if key == "medications" else key
            
            if key == "allergies":
                update_push["allergies"] = {"$each": [a for a in extracted_data["allergies"] if isinstance(a, str) and a.strip()]}
            else:
                 update_push[db_key] = {"$each": [item for item in extracted_data[key] if isinstance(item, dict)]}

    await medical_records_collection.update_one(
        {"patient_id": patient['email']},
        {"$set": {"updated_at": datetime.utcnow()}, "$push": update_push},
        upsert=True
    )

    return JSONResponse({"message": "Saved and parsed successfully", "extracted_data": extracted_data})

@router.post("/set-availability", tags=["Doctor"])
async def set_doctor_availability(
    status: str = Body(..., embed=True), 
    current_user: User = Depends(get_current_doctor)
):
    """
    Updates doctor's availability status.
    Uses a FRESH database check to ensure the 'Public' status is accurate.
    """
    valid_statuses = ["available", "busy", "cooldown", "offline"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status provided.")

    # --- 1. ROBUST CHECK: Fetch latest status directly from DB ---
    # We do not trust 'current_user' here because it might be outdated (stale session).
    fresh_user_data = await user_collection.find_one({"email": current_user.email})
    
    if not fresh_user_data:
        raise HTTPException(status_code=404, detail="User record not found.")

    # Get the real-time 'is_public' value
    is_public_live = fresh_user_data.get("is_public", False)

    # --- 2. VALIDATION RULE ---
    if status == "available" and not is_public_live:
        raise HTTPException(
            status_code=400, 
            detail="Your profile is currently PRIVATE. Please switch to PUBLIC using the toggle in the top menu."
        )

    # --- 3. UPDATE STATUS ---
    await user_collection.update_one(
        {"email": current_user.email},
        {"$set": {"availability_status": status}}
    )
    
    return {"message": f"Status updated to {status}", "current_status": status}

@router.post("/patient/{patient_id}/generate-report-text",tags=["Doctor"])
async def generate_medical_report_text_endpoint(
    patient_id: str,
    body: Dict[str, str] = Body(...), 
    current_user: User = Depends(get_current_doctor)
):
    transcribed_text = body.get('transcribed_text')
    if not transcribed_text:
        raise HTTPException(status_code=400, detail="No transcribed text provided.")

    patient = await user_collection.find_one({"aarogya_id": patient_id})
    if not patient:
         try:
            patient = await user_collection.find_one({"_id": ObjectId(patient_id)})
         except: pass
         
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    context = await fetch_patient_context(patient['email'])
    
    formatted_report_text = await chatbot_service.generate_medical_report(
        patient_data=context,
        doctor_data=current_user.model_dump(),
        transcribed_text=transcribed_text
    )

    return JSONResponse({"report_text": formatted_report_text})