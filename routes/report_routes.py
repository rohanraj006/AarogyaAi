# routes/report_routes.py
import os
import fitz # PyMuPDF
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Body, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List
from bson import ObjectId
from fpdf import FPDF
import asyncio
from datetime import datetime

# Database & Auth
from models.schemas import MedicalRecord, User, Report, ReportContentRequest
from security import get_current_authenticated_user
from database import reports_collection, user_collection, medical_records_collection, report_contents_collection

# NEW AI Service (Replaces RAG Engine)
from ai_core.chatbot_service import MedicalChatbot

router = APIRouter()
chatbot = MedicalChatbot()

@router.post("/upload")
async def upload_report(
    current_user: User = Depends(get_current_authenticated_user),
    file: UploadFile = File(...)
):
    """
    Uploads a user's report. Extracts text and saves it to MongoDB.
    (Pinecone ingestion has been removed).
    """
    
    file_content = await file.read()
    
    # Helper to run synchronous PDF parsing in a thread
    def extract_text_sync():
        extracted_text = ""
        try:
            if file.content_type == 'application/pdf':
                with fitz.open(stream=file_content, filetype="pdf") as doc:
                    extracted_text = "".join(page.get_text() for page in doc)
            elif file.content_type == 'text/plain':
                extracted_text = file_content.decode('utf-8')
        except Exception as e:
            print(f"Error extracting text: {e}")
        return extracted_text

    extracted_text = await asyncio.to_thread(extract_text_sync)
        
    if not extracted_text:
        # We still allow the upload even if text extraction fails, but warn/log it
        print(f"Warning: Could not extract text from {file.filename}")
        extracted_text = "Content could not be extracted automatically."

    # 1. Save content to dedicated collection
    content_doc = {"content_text": extracted_text, "upload_date": datetime.utcnow()} 
    insert_content_result = await report_contents_collection.insert_one(content_doc) 
    content_id = str(insert_content_result.inserted_id)
    
    # 2. Save the report reference
    report_data = Report(
        filename=file.filename,
        owner_email=current_user.email,
        content_id=content_id, 
        report_type=f"User Upload ({file.content_type.split('/')[-1].upper()})",
    )
    
    await reports_collection.insert_one(report_data.model_dump(by_alias=True, exclude_none=True)) 
    
    return {"message": f"Successfully uploaded {file.filename}."}

@router.post("/doctor/add_report")
async def doctor_add_report(
    current_user: User = Depends(get_current_authenticated_user),
    patient_email: str = Body(...),
    report_content: str = Body(...),
    filename: str = Body("Doctor's Note")
):
    """Allows a connected doctor to add a new text-based report for a patient."""
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can add reports.")
    
    if not current_user.is_authorized:
        raise HTTPException(status_code=403, detail="Unauthorized access.")

    patient = await user_collection.find_one({"email": patient_email})
    if not patient or patient_email not in current_user.patient_list:
        raise HTTPException(status_code=403, detail="You are not connected to this patient.")

    # 1. Save content
    content_doc = {"content_text": report_content, "upload_date": datetime.utcnow()}
    insert_content_result = await report_contents_collection.insert_one(content_doc)
    content_id = str(insert_content_result.inserted_id)

    # 2. Save reference
    report_data = Report(
        filename=filename,
        owner_email=patient_email,
        content_id=content_id,
        report_type="Doctor's Manual Note"
    )

    await reports_collection.insert_one(report_data.model_dump(by_alias=True, exclude_none=True))

    return {"message": f"Successfully added report for {patient_email}."}

@router.get("/my-reports", response_model=List[Report])
async def get_user_reports(current_user: User = Depends(get_current_authenticated_user)):
    """Retrieves all reports for the current user."""
    reports_cursor = reports_collection.find({"owner_email": current_user.email}).sort("upload_date", -1)
    reports_list = await reports_cursor.to_list(length=100)
    
    validated_reports = []
    for report in reports_list:
        if '_id' in report: report['_id'] = str(report['_id'])
        if 'content_id' in report: report['content_id'] = str(report['content_id'])
        validated_reports.append(Report.model_validate(report))
        
    return validated_reports

@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(report_id: str, current_user: User = Depends(get_current_authenticated_user)):
    """Deletes a report and its content."""
    try:
        report_oid = ObjectId(report_id)
        report = await reports_collection.find_one({"_id": report_oid})
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid Report ID format.")
         
    if not report or report["owner_email"] != current_user.email:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # 1. Delete content (Pinecone deletion removed)
    if report.get("content_id"):
        try:
            await report_contents_collection.delete_one({"_id": ObjectId(report["content_id"])})
        except Exception:
            pass 
    
    # 2. Delete reference
    await reports_collection.delete_one({"_id": report_oid})
    return

@router.get("/{report_id}/download")
async def download_report_as_pdf(
    report_id: str, 
    background_tasks: BackgroundTasks, 
    current_user: User = Depends(get_current_authenticated_user)
):
    """Downloads the report content as a PDF."""
    try:
        report = await reports_collection.find_one({"_id": ObjectId(report_id)})
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid Report ID.")

    if not report or report["owner_email"] != current_user.email:
        raise HTTPException(status_code=404, detail="Report not found")
        
    content_id = report.get("content_id")
    if not content_id:
        raise HTTPException(status_code=400, detail="Report has no stored content.")

    content_doc = await report_contents_collection.find_one({"_id": ObjectId(content_id)})
    report_content = content_doc.get("content_text") if content_doc else None
    
    if not report_content:
        raise HTTPException(status_code=404, detail="Report content is empty.")
    
    def generate_fpdf(content, filename):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf_text = content.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 10, txt=pdf_text)
        temp_path = f"temp_{filename}_{os.getpid()}.pdf"
        pdf.output(temp_path)
        return temp_path

    temp_pdf_path = await asyncio.to_thread(generate_fpdf, report_content, report_id)
    background_tasks.add_task(os.remove, temp_pdf_path)
    
    return FileResponse(
        temp_pdf_path,
        media_type='application/pdf',
        filename=f"{os.path.splitext(report['filename'])[0]}.pdf"
    )

@router.post("/{report_id}/summarize")
async def summarize_report(report_id: str, current_user: User = Depends(get_current_authenticated_user)):
    """Summarizes a SINGLE report using the new Chatbot Service."""
    try:
        report = await reports_collection.find_one({"_id": ObjectId(report_id)})
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid ID.")

    if not report or report["owner_email"] != current_user.email:
        raise HTTPException(status_code=404, detail="Report not found")

    content_doc = await report_contents_collection.find_one({"_id": ObjectId(report.get("content_id"))})
    report_content = content_doc.get("content_text") if content_doc else None

    if not report_content:
         return {"filename": report['filename'], "summary": "Empty report."}

    # Use the new service
    summary = await chatbot.summarize_report_text(report_content)

    return {"filename": report['filename'], "summary": summary}

@router.get("/patient-by-id/{patient_aarogya_id}", response_model=List[Report], tags=["Reports"])
async def get_patient_reports_for_doctor(patient_aarogya_id: str, current_user: User = Depends(get_current_authenticated_user)):
    """Allows doctor to view patient reports."""
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Access denied.")
    
    patient = await user_collection.find_one({"aarogya_id": patient_aarogya_id})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    
    if patient["email"] not in current_user.patient_list:
        raise HTTPException(status_code=403, detail="Patient not connected.")
        
    reports_cursor = reports_collection.find({"owner_email": patient["email"]}).sort("upload_date", -1)
    reports_list = await reports_cursor.to_list(length=100)

    validated_reports = []
    for report in reports_list:
        if '_id' in report: report['_id'] = str(report['_id'])
        if 'content_id' in report: report['content_id'] = str(report['content_id'])
        validated_reports.append(Report.model_validate(report))
        
    return validated_reports

@router.get("/my-structured-record", response_model=MedicalRecord, tags=["Reports"])
async def get_my_structured_record(current_user: User = Depends(get_current_authenticated_user)):
    """Retrieves the patient's structured record."""
    if current_user.user_type != "patient":
        raise HTTPException(status_code=403, detail="Access denied.")
        
    record = await medical_records_collection.find_one({"patient_id": current_user.email})
    return MedicalRecord(**record) if record else MedicalRecord(patient_id=current_user.email)

@router.get("/doctor/download/{report_id}")
async def doctor_download_patient_report(
    report_id: str,
    background_tasks: BackgroundTasks, 
    current_user: User = Depends(get_current_authenticated_user)
):
    """Doctor download route."""
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Access denied.")
        
    report = await reports_collection.find_one({"_id": ObjectId(report_id)})
    if not report: raise HTTPException(404, "Report not found")
    
    if report["owner_email"] not in current_user.patient_list:
        raise HTTPException(403, "Not connected to patient.")
    
    content_doc = await report_contents_collection.find_one({"_id": ObjectId(report["content_id"])})
    # ... reuse generation logic or abstract it ...
    # For brevity, reusing the same FPDF logic here:
    
    def generate_fpdf(content, filename):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf_text = content.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 10, txt=pdf_text)
        temp_path = f"temp_{filename}_{os.getpid()}.pdf"
        pdf.output(temp_path)
        return temp_path

    temp_path = await asyncio.to_thread(generate_fpdf, content_doc.get("content_text", ""), report_id)
    background_tasks.add_task(os.remove, temp_path)
    return FileResponse(temp_path, media_type='application/pdf', filename=f"{report['filename']}.pdf")

@router.post("/doctor/summarize/{report_id}")
async def doctor_summarize_patient_report(
    report_id: str, 
    current_user: User = Depends(get_current_authenticated_user)
):
    """Doctor summary route."""
    if current_user.user_type != "doctor": raise HTTPException(403)

    report = await reports_collection.find_one({"_id": ObjectId(report_id)})
    if not report: raise HTTPException(404)

    if report["owner_email"] not in current_user.patient_list: raise HTTPException(403)

    content_doc = await report_contents_collection.find_one({"_id": ObjectId(report["content_id"])})
    summary = await chatbot.summarize_report_text(content_doc.get("content_text", ""))

    return {"filename": report['filename'], "summary": summary}