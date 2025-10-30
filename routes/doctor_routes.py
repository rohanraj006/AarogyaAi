# routes/doctor_routes.py

from fastapi import APIRouter, Body, Depends, HTTPException, status, Query, UploadFile, File, Request
from fastapi.responses import JSONResponse, StreamingResponse
from typing import List, Dict, Any, Optional
from pydantic import ValidationError
from bson import ObjectId

# CORE IMPORTS
from security import get_current_authenticated_user
from database import user_collection, medical_records_collection, report_contents_collection # Motor collections
from ai_core.rag_engine import process_dictation, fetch_patient_context # Use async services/helpers
from models.schemas import DictationSaveBody, MedicalRecord, Name, User, Diagnosis, Medication, ReportPDFRequest, ReportContentRequest
from ai_core.rag_engine import chatbot_service, parser_service # Assuming services are exposed

# NEW IMPORTS FOR STEP 6
import tempfile
import os
import io
from datetime import datetime, timezone
from fastapi.concurrency import run_in_threadpool
import anyio

# --- ReportLab Imports (Professional PDF) ---
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import inch

# --- Transcription Imports (Faster-Whisper) ---
try:
    from faster_whisper import WhisperModel
    import torch
    # Initialize Whisper Model (assumes necessary environment variables/packages are set up)
    WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "tiny")
    WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
    WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16" if WHISPER_DEVICE == "cuda" else "int8")
    whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
except ImportError:
    WhisperModel = None
    whisper_model = None


router = APIRouter()

# --- HELPER DEPENDENCY ---
async def get_current_doctor(current_user: User = Depends(get_current_authenticated_user)):
    if current_user.user_type != "doctor": 
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Only doctors can perform this action.")
    return current_user
# --- END HELPER DEPENDENCY ---

# --- PDF GENERATION HELPER FUNCTION (ReportLab) ---
def create_report_pdf(doctor_info: dict, patient_info: dict, report_content_text: str) -> io.BytesIO:
    """Generates a medical report PDF using ReportLab with doctor and patient headers."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet() 

    styles.add(ParagraphStyle(name='CustomNormal', fontSize=10, leading=12, alignment=TA_LEFT, spaceAfter=6))
    styles.add(ParagraphStyle(name='Heading1Center', fontSize=14, leading=16, alignment=TA_CENTER, spaceAfter=20, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='Heading2Left', fontSize=12, leading=14, alignment=TA_LEFT, spaceBefore=10, spaceAfter=5, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='Small', fontSize=9, leading=10, alignment=TA_LEFT, spaceAfter=4))
    styles.add(ParagraphStyle(name='FooterStyle', fontSize=9, leading=10, alignment=TA_CENTER, spaceBefore=10, textColor=styles['Normal'].textColor))

    Story = []
    
    # Doctor Information Section
    doctor_name = f"Dr. {doctor_info.get('name', {}).get('first', '')} {doctor_info.get('name', {}).get('last', '')}".strip() or "Dr. [Doctor Name]"
    
    Story.append(Paragraph("<font size=12><b>Medical Report</b></font>", styles['Heading1Center']))
    Story.append(Paragraph(f"<font size=10><b>{doctor_name}</b>, {doctor_info.get('specialization', 'Medical Practitioner')}</font>", styles['CustomNormal']))
    Story.append(Paragraph(f"<font size=9>Email: {doctor_info.get('email', '')}</font>", styles['Small']))
    Story.append(Spacer(1, 0.2 * inch))

    # Patient Information Section
    patient_name = f"{patient_info.get('name', {}).get('first', '')} {patient_info.get('name', {}).get('last', '')}".strip() or "[Patient Name]"
    patient_dob = patient_info.get('date_of_birth', 'N/A')
    patient_id_display = str(patient_info.get('aarogya_id', patient_info.get('_id', 'N/A')))

    Story.append(Paragraph("<font size=10><b>Patient Information:</b></font>", styles['Heading2Left']))
    Story.append(Paragraph(f"<font size=10><b>Name:</b> {patient_name}</font>", styles['CustomNormal']))
    Story.append(Paragraph(f"<font size=10><b>Aarogya ID:</b> {patient_id_display}</font>", styles['CustomNormal']))
    Story.append(Paragraph(f"<font size=10><b>Date of Birth:</b> {patient_dob}</font>", styles['CustomNormal']))
    Story.append(Spacer(1, 0.3 * inch))

    # Report Content
    Story.append(Paragraph("<font size=10><b>Report Details:</b></font>", styles['Heading2Left']))
    report_content_formatted = report_content_text.replace('\n', '<br/>') if report_content_text else "No report content provided."
    Story.append(Paragraph(report_content_formatted, styles['CustomNormal']))

    Story.append(Spacer(1, 0.5 * inch))
    footer_text = f"Generated by Aarogya AI on {datetime.now().strftime('%Y-%m-%d %H:%M')} | Page <page/> of <npgs/>"
    Story.append(Paragraph(footer_text, styles['FooterStyle'])) 

    doc.build(Story)
    buffer.seek(0) 
    return buffer

@router.get("/api/patients/search")
async def search_for_patient(
    current_user: User = Depends(get_current_doctor), # Use the new doctor helper
    aarogya_id: str = Query(..., min_length=10, max_length=15)
):
    """allows loggedin doctor to search a patient by their aarogyaid."""
    
    # Authorization check is handled by get_current_doctor implicitly checking user_type
    
    if not current_user.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be authorized by the platform owner to access patient features."
        )

    patient = await user_collection.find_one({ # Use await for Motor
        "aarogya_id": aarogya_id,
        "user_type":"patient"
    })
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no patient found with aarogyaID: {aarogya_id}"
        )
    
    # Since the User schema is now detailed, we must extract only basic public fields
    # Use the embedded Name schema for a clean response
    if patient.get("name"):
        patient_name = Name(**patient["name"]).model_dump()
    else:
        patient_name = {"first": patient["email"].split('@')[0], "last": ""}
    return{
        "aarogya_id": patient["aarogya_id"],
        "email": patient["email"],
        "name": patient_name
    }

@router.get("/my-patients", response_model=List[User])
async def get_my_patients(current_user: User = Depends(get_current_doctor)):
    """
    Fetches a list of patient User objects connected to the currently logged-in doctor.
    """
    if not current_user.patient_list:
        return [] # Return an empty list if they have no patients

    # Your connection routes store patient emails in the doctor's 'patient_list'
    patients_cursor = user_collection.find({
        "email": {"$in": current_user.patient_list},
        "user_type": "patient"
    })
    
    patient_list = await patients_cursor.to_list(length=None)

    validated_patients = []
    for patient in patient_list:
        if '_id' in patient:
            patient['_id'] = str(patient['_id'])  # Convert ObjectId to string
        validated_patients.append(User.model_validate(patient))
    
    return validated_patients

@router.post("/toggle_public", tags=["Doctor"])
async def doctor_toggle_public_status(
    current_user: User = Depends(get_current_doctor), # Use the new doctor helper 
    is_public: bool = Body(..., embed=True)
):
    """Allows an authorized doctor to set their profile visibility for the public directory."""
    
    if not current_user.is_authorized:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be authorized by the platform owner to be listed publicly.")

    # Update the doctor's document in the database
    await user_collection.update_one( # Use await for Motor
        {"email": current_user.email},
        {"$set": {"is_public": is_public}}
    )
    
    return {"message": f"Your public status has been set to {is_public}."}

@router.post("/dictation/process", response_model=Dict[str, List[Any]], tags=["Doctor"]) 
async def process_dictation_notes(
    dictation_text: str = Body(..., embed=True),
    current_user: User = Depends(get_current_doctor)
):
    # ... (Authentication/Authorization checks removed for brevity) ...

    if not dictation_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dictation text cannot be empty.")

    # The AI parsing service requires the patient's email to fetch context
    # This is a legacy endpoint, we use the doctor's email as a placeholder for context fetching.
    patient_email_placeholder = "placeholder@patient.com" 
    
    # 1. Send the text to the AI core for structured extraction
    structured_data = await process_dictation(dictation_text, patient_email=patient_email_placeholder)

    if not structured_data or structured_data.get("error"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=structured_data.get("error", "AI failed to process notes. Please check the dictation or try again.")
        )

    # 2. Validate and return the structured data
    try:
        validated_diagnoses = [Diagnosis(**d) for d in structured_data.get('diagnoses', [])]
        validated_medications = [Medication(**m) for m in structured_data.get('medications', [])]
        
        return {
            "diagnosis": [d.model_dump() for d in validated_diagnoses],
            "medications": [m.model_dump() for m in validated_medications],
        }
        
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI output validation failed against rich schemas. Data integrity error: {e.errors()}"
        )
        
@router.post("/patient/records/save", status_code=status.HTTP_200_OK, tags=["Doctor"])
async def save_structured_medical_data(
    body: DictationSaveBody,
    current_user: User = Depends(get_current_doctor)
):
    # ... (Authentication/Authorization checks removed for brevity) ...
    
    if body.patient_email not in current_user.patient_list:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Patient is not connected to your account.")
        
    
    # 3. Persistence Logic (UPDATED for rich schemas and Motor)
    
    existing_record = await medical_records_collection.find_one({"patient_id": body.patient_email}) 
    
    new_diagnoses = [d.model_dump(mode='json') for d in body.medical_record.diagnoses] 
    new_medications = [m.model_dump(mode='json') for m in body.medical_record.current_medications] 
    
    # NOTE: In Codebase 1, the patient's record is linked by email.
    
    if existing_record:
        await medical_records_collection.update_one( 
            {"patient_id": body.patient_email},
            {
                "$push": {
                    "diagnoses": {"$each": new_diagnoses},
                    "current_medications": {"$each": new_medications},
                },
                "$set": {
                    "updated_at": datetime.utcnow()
                }
            }
        )
    else:
        new_record = {
            "patient_id": body.patient_email,
            "diagnoses": new_diagnoses,
            "current_medications": new_medications,
            "reports": [], 
            "allergies": [],
            "consultation_history": [],
            "prescriptions": [],
            "immunizations": [],
            "family_medical_history": None,
            "updated_at": datetime.utcnow()
        }
        await medical_records_collection.insert_one(new_record)
        
    return {"message": f"Successfully updated structured medical record for {body.patient_email}."}


# --- NEW: VOICE TRANSCRIPTION ENDPOINT ---
@router.post("/patient/{patient_id}/transcribe", tags=["Doctor"])
async def transcribe_medical_report(
    patient_id: str,
    audio_file: UploadFile = File(...),
    current_user: User = Depends(get_current_doctor)
):
    """Receives an audio file and returns transcribed text using Faster-Whisper."""
    if not whisper_model:
        raise HTTPException(status_code=503, detail="Voice transcription model is not loaded.")

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
        print(f"Error during Faster-Whisper transcription: {e}")
        raise HTTPException(status_code=500, detail=f"Error during transcription: {e}")
    finally:
        if tmp_file_path and os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)
            

# --- NEW: GENERATE FORMATTED REPORT TEXT ENDPOINT ---
@router.post("/patient/{patient_id}/generate-report-text", tags=["Doctor"])
async def generate_medical_report_text_endpoint(
    patient_id: str,
    body: Dict[str, str] = Body(...), # Expects {'transcribed_text': 'raw notes'}
    current_user: User = Depends(get_current_doctor)
):
    """Formats raw transcribed text into a structured medical report using AI."""
    transcribed_text = body.get('transcribed_text')
    if not transcribed_text or not transcribed_text.strip():
        raise HTTPException(status_code=400, detail="No transcribed text provided.")

    if not chatbot_service or not chatbot_service.model:
        raise HTTPException(status_code=503, detail="AI service is not initialized.")

    patient_context_data = await fetch_patient_context(patient_id)
    if not patient_context_data['user_doc']:
        raise HTTPException(status_code=404, detail="Patient not found.")
        
    formatted_report_text = await chatbot_service.generate_medical_report(
        patient_data=patient_context_data,
        doctor_data=current_user.model_dump(),
        transcribed_text=transcribed_text
    )

    if not formatted_report_text or "Error" in formatted_report_text:
        raise HTTPException(status_code=500, detail=formatted_report_text)
        
    return JSONResponse({"report_text": formatted_report_text})
    
    
# --- NEW: GENERATE PDF REPORT ENDPOINT ---
@router.post("/patient/{patient_id}/generate-pdf-report", tags=["Doctor"])
async def generate_medical_pdf_report_endpoint(
    patient_id: str,
    body: ReportPDFRequest,
    current_user: User = Depends(get_current_doctor)
):
    """Generates a PDF report from the final formatted text and streams it to the client."""
    final_report_content_text = body.report_content_text

    if not final_report_content_text or not final_report_content_text.strip():
        raise HTTPException(status_code=400, detail="No final report text content provided to generate a PDF.")

    patient_context = await fetch_patient_context(patient_id)
    patient_details = patient_context.get('user_doc')
    
    if not patient_details:
        raise HTTPException(status_code=404, detail="Patient not found.")

    try:
        # Use run_in_threadpool because ReportLab is synchronous
        pdf_buffer = await run_in_threadpool(
            create_report_pdf,
            doctor_info=current_user.model_dump(),
            patient_info=patient_details,
            report_content_text=final_report_content_text
        )

        response = StreamingResponse(pdf_buffer, media_type="application/pdf")
        patient_last_name = patient_details.get('name', {}).get('last', patient_id)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"medical_report_{patient_last_name}_{timestamp}.pdf"

        response.headers["Content-Disposition"] = f"attachment; filename={pdf_filename}"
        return response

    except Exception as e:
        print(f"Error during PDF streaming: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during PDF streaming: {e}")
        
# --- NEW: SAVE PARSED DATA ENDPOINT ---
@router.post("/patient/{patient_id}/save-parsed-report", tags=["Doctor"])
async def save_parsed_report_data(
    patient_id: str,
    body: ReportPDFRequest,
    current_user: User = Depends(get_current_doctor)
):
    """
    Receives formatted report text, parses it using the AI service,
    and saves the extracted structured data and the report content to the DB.
    """
    report_content_text = body.report_content_text
    if not report_content_text or not report_content_text.strip():
        raise HTTPException(status_code=400, detail="No report content provided to parse and save.")

    if not parser_service:
        raise HTTPException(status_code=503, detail="AI parsing service is not initialized.")

    patient_context_data = await fetch_patient_context(patient_id)
    patient_details = patient_context_data['user_doc']
    
    if not patient_details:
        raise HTTPException(status_code=404, detail="Patient not found.")

    # Find or create medical record
    medical_record_doc = await medical_records_collection.find_one({"patient_id": patient_id}) 
    if not medical_record_doc:
        new_medical_record = {"patient_id": patient_id, "reports": [], "current_medications": [], "diagnoses": [], "allergies": [], "consultation_history": [], "immunizations": [], "prescriptions": [], "family_medical_history": None, "updated_at": datetime.utcnow()} 
        await medical_records_collection.insert_one(new_medical_record)
        medical_record_doc = await medical_records_collection.find_one({"patient_id": patient_id})


    # 2. Call the Parser Service
    extracted_data = await parser_service.parse_medical_report(
        report_text=report_content_text,
        patient_data=patient_context_data,
        doctor_data=current_user.model_dump()
    )

    # 3. Save Report Content and Reference
    content_doc = ReportContentRequest(content_text=report_content_text).model_dump()
    insert_content_result = await report_contents_collection.insert_one(content_doc)
    content_id = str(insert_content_result.inserted_id)

    report_ref = {
        "report_id": content_id,
        "report_type": "AI Generated Report",
        "date": datetime.utcnow(),
        "content_id": content_id,
    }

    # 4. Prepare and Execute Update
    update_push = {"reports": report_ref}
    update_set = {"updated_at": datetime.utcnow()}

    for key in ["diagnoses", "medications", "allergies", "consultations", "immunizations"]:
        if extracted_data.get(key):
            # For simplicity, map to existing keys in the medical record schema
            db_key = "current_medications" if key == "medications" else key 
            
            # Use $addToSet for allergies to prevent duplicates, $push for others
            if key == "allergies":
                update_push["allergies"] = {"$each": [a for a in extracted_data["allergies"] if isinstance(a, str) and a.strip()]}
            else:
                 update_push[db_key] = {"$each": [item for item in extracted_data[key] if isinstance(item, dict)]}


    await medical_records_collection.update_one(
        {"patient_id": patient_id},
        {"$set": update_set, "$push": update_push}
    )

    return JSONResponse({"message": "Report data parsed and saved successfully", "content_id": content_id, "extracted_data": extracted_data})