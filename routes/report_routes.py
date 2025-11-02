# routes/report_routes.py
import os
import fitz # PyMuPDF (synchronous)
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Body, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List
from bson import ObjectId
from fpdf import FPDF # Used for basic PDF download route
import asyncio # Used to run synchronous code in a threadpool
from datetime import datetime

# UPDATED IMPORTS
from models.schemas import MedicalRecord, User, Report, ReportContentRequest
from security import get_current_authenticated_user
from database import reports_collection, user_collection, medical_records_collection, report_contents_collection # Motor collections
from ai_core.rag_engine import get_summary_response, pinecone_index, embedding_model, chatbot_service # get_summary_response is now async service wrapper

router = APIRouter()

# --- Improved Chunking Helper Function (Synchronous, for Pinecone) ---
def get_chunks_with_overlap(text: str, chunk_size: int = 512, chunk_overlap: int = 50) -> List[str]:
    """Splits text into chunks with a sliding window for better context continuity."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk.strip())
        
        if end >= len(text):
            break
        
        start += chunk_size - chunk_overlap
    
    return chunks

# --- Helper function for Pinecone ingestion (Synchronous, for threadpool) ---
def ingest_text_to_pinecone(text: str, owner_email: str, filename: str):
    """Helper function to vectorize and upsert text to Pinecone. Runs synchronously."""
    if not text or not pinecone_index:
        return

    chunks = get_chunks_with_overlap(text) 
    
    if chunks:
        vectors = embedding_model.encode(chunks).tolist()
        metadata = [{"owner_email": owner_email, "filename": filename, "text": chunk} for chunk in chunks]
        ids = [f"{owner_email}_{filename}_{i}" for i in range(len(chunks))]
        pinecone_index.upsert(vectors=zip(ids, vectors, metadata))


@router.post("/upload")
async def upload_report(
    current_user: User = Depends(get_current_authenticated_user),
    file: UploadFile = File(...)
):
    """Uploads a user's report. The file content is stored in a separate collection and vectorized."""
    
    file_content = await file.read()
    
    # Run synchronous file parsing in a threadpool to avoid blocking
    def extract_text_sync():
        extracted_text = ""
        if file.content_type == 'application/pdf':
            with fitz.open(stream=file_content, filetype="pdf") as doc:
                extracted_text = "".join(page.get_text() for page in doc)
        elif file.content_type == 'text/plain':
            extracted_text = file_content.decode('utf-8')
        return extracted_text

    extracted_text = await asyncio.to_thread(extract_text_sync)
        
    if not extracted_text:
        raise HTTPException(status_code=400, detail="Could not extract text from file.")

    # 1. Ingest text to Pinecone (run synchronously in a threadpool)
    await asyncio.to_thread(ingest_text_to_pinecone, extracted_text, current_user.email, file.filename)
            
    # 2. Save content to dedicated collection
    # NOTE: Using a dictionary for insertion for simplicity in the absence of the explicit ReportContent model
    content_doc = {"content_text": extracted_text, "upload_date": datetime.utcnow()} 
    insert_content_result = await report_contents_collection.insert_one(content_doc) 
    content_id = str(insert_content_result.inserted_id)
    
    # 3. Save the report reference to the primary reports collection
    report_data = Report(
        filename=file.filename,
        owner_email=current_user.email,
        content_id=content_id, # Store reference ID
        report_type=f"User Upload ({file.content_type.split('/')[-1].upper()})",
    )
    
    await reports_collection.insert_one(report_data.model_dump(by_alias=True,exclude_none=True)) 
    
    return {"message": f"Successfully uploaded and ingested {file.filename}."}

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
    
    if current_user.user_type == "doctor" and not current_user.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be authorized by the platform owner to use the AI summarization feature."
        )

    patient = await user_collection.find_one({"email": patient_email})
    if not patient or patient_email not in current_user.patient_list:
        raise HTTPException(status_code=403, detail="You are not connected to this patient.")

    # 1. Ingest text to Pinecone (run synchronously in a threadpool)
    await asyncio.to_thread(ingest_text_to_pinecone, report_content, patient_email, filename)
    
    # 2. Save content to dedicated collection
    content_doc = {"content_text": report_content, "upload_date": datetime.utcnow()}
    insert_content_result = await report_contents_collection.insert_one(content_doc)
    content_id = str(insert_content_result.inserted_id)

    # 3. Save the report reference
    report_data = Report(
        filename=filename,
        owner_email=patient_email,
        content_id=content_id,
        report_type="Doctor's Manual Note"
    )

    await reports_collection.insert_one(report_data.model_dump(by_alias=True,exclude_none=True))

    return {"message": f"Successfully added report for {patient_email}."}


@router.get("/my-reports", response_model=List[Report])
async def get_user_reports(current_user: User = Depends(get_current_authenticated_user)):
    """
    Retrieves all reports for the current user.
    """
    reports_cursor = reports_collection.find({"owner_email": current_user.email}).sort("upload_date", -1)
    reports_list = await reports_cursor.to_list(length=100)
    
    # Attach content_id for subsequent calls
    validated_reports = []
    for report in reports_list:
        if '_id' in report:
            report['_id'] = str(report['_id'])
        if 'content_id' in report and report['content_id'] is not None:
             report['content_id'] = str(report['content_id'])
        validated_reports.append(Report.model_validate(report))
        
    return validated_reports

@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(report_id: str, current_user: User = Depends(get_current_authenticated_user)):
    """
    Deletes a report and all its associated vectors from Pinecone, and deletes the content document.
    """
    try:
        report_oid = ObjectId(report_id)
        report = await reports_collection.find_one({"_id": report_oid})
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid Report ID format.")
         
    if not report or report["owner_email"] != current_user.email:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # 1. Delete from Pinecone (run synchronously in a threadpool)
    if pinecone_index:
        await asyncio.to_thread(pinecone_index.delete, 
            filter={
                "owner_email": report['owner_email'],
                "filename": report['filename']
            }
        )
    
    # 2. Delete the content document (if reference exists)
    if report.get("content_id"):
        try:
            await report_contents_collection.delete_one({"_id": ObjectId(report["content_id"])})
        except Exception:
            print(f"Warning: Failed to delete content document {report['content_id']}")
    
    # 3. Delete the report reference document
    await reports_collection.delete_one({"_id": report_oid})
    return

@router.get("/{report_id}/download")
async def download_report_as_pdf(report_id: str, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_authenticated_user)):
    """
    Downloads the report content as a basic PDF using FPDF, fetching content from the dedicated collection.
    """
    try:
        report = await reports_collection.find_one({"_id": ObjectId(report_id)})
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid Report ID format.")

    if not report or report["owner_email"] != current_user.email:
        raise HTTPException(status_code=404, detail="Report not found")
        
    content_id = report.get("content_id")
    if not content_id:
        raise HTTPException(status_code=400, detail="Report has no stored content ID.")

    try:
        content_doc = await report_contents_collection.find_one({"_id": ObjectId(content_id)})
        report_content = content_doc.get("content_text") if content_doc else None
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid Content ID format or DB error.")
    
    if not report_content:
        raise HTTPException(status_code=404, detail="Report content not found or is empty.")
    
    # Synchronous FPDF logic must be run in a threadpool
    def generate_fpdf(content, filename):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        pdf_text = content.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 10, txt=pdf_text)
        
        temp_pdf_path = f"temp_{filename}_{os.getpid()}.pdf"
        pdf.output(temp_pdf_path)
        return temp_pdf_path

    temp_pdf_path = await asyncio.to_thread(generate_fpdf, report_content, report_id)
    background_tasks.add_task(os.remove, temp_pdf_path)
    return FileResponse(
        temp_pdf_path,
        media_type='application/pdf',
        filename=f"{os.path.splitext(report['filename'])[0]}.pdf"
    )

@router.post("/{report_id}/summarize")
async def summarize_report(report_id: str, current_user: User = Depends(get_current_authenticated_user)):
    """
    Summarizes the content of a SINGLE report, not the whole patient record.
    """
    try:
        report = await reports_collection.find_one({"_id": ObjectId(report_id)})
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid Report ID format.")

    if not report or report["owner_email"] != current_user.email:
        raise HTTPException(status_code=404, detail="Report not found")

    content_id_str = report.get("content_id")
    if not content_id_str:
        raise HTTPException(status_code=404, detail="Report has no content to summarize.")

    try:
        content_doc = await report_contents_collection.find_one({"_id": ObjectId(content_id_str)})
        report_content = content_doc.get("content_text") if content_doc else None
    except Exception:
        raise HTTPException(status_code=404, detail="Could not find report content.")

    if not report_content:
         return {"filename": report['filename'], "summary": "This report content is empty."}

    if not chatbot_service:
        raise HTTPException(status_code=503, detail="AI Summary service is not available.")

    # Call the new service to summarize the text
    try:
        summary = await chatbot_service.summarize_report_text(report_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating summary: {e}")

    return {"filename": report['filename'], "summary": summary}

@router.get("/patient-by-id/{patient_aarogya_id}", response_model=List[Report], tags=["Reports"])
async def get_patient_reports_for_doctor(patient_aarogya_id: str, current_user: User = Depends(get_current_authenticated_user)):
    """Allows an authorized doctor to view the reports of a patient on their list using Patient ID."""
    
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Access denied. Only doctors can view patient records.")
    
    if not current_user.is_authorized:
        raise HTTPException(status_code=403, detail="You must be authorized by the platform owner to access patient records.")

    # --- NEW LOGIC: Find patient by ID to get their email ---
    patient = await user_collection.find_one({"aarogya_id": patient_aarogya_id, "user_type": "patient"})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found with this ID.")
    
    patient_email = patient["email"]
    # --- END NEW LOGIC ---

    if patient_email not in current_user.patient_list:
        raise HTTPException(status_code=403, detail="Access denied. Patient is not connected to your account.")
        
    reports_cursor = reports_collection.find({"owner_email": patient_email}).sort("upload_date", -1)
    # ... (rest of the function remains the same, including the 'validated_reports' fix)
    reports_list = await reports_cursor.to_list(length=100)

    validated_reports = []
    for report in reports_list:
        if '_id' in report:
            report['_id'] = str(report['_id'])
        if 'content_id' in report and report['content_id'] is not None:
             report['content_id'] = str(report['content_id'])
        validated_reports.append(Report.model_validate(report))
        
    return validated_reports

@router.get("/my-structured-record", response_model=MedicalRecord, tags=["Reports"])
async def get_my_structured_record(current_user: User = Depends(get_current_authenticated_user)):
    """Retrieves the patient's complete structured medical record (diagnoses and medications)."""
    
    if current_user.user_type != "patient":
        raise HTTPException(status_code=403, detail="Access denied. Only patients can view their own record here.")
        
    # The medical record is keyed by the patient's email in this codebase's structure.
    record = await medical_records_collection.find_one({"patient_id": current_user.email})

    if not record:
        # If no record exists, return an empty default MedicalRecord object
        return MedicalRecord(patient_id=current_user.email)
        
    return MedicalRecord(**record)

@router.get("/doctor/download/{report_id}")
async def doctor_download_patient_report(
    report_id: str,
    background_tasks: BackgroundTasks, 
    current_user: User = Depends(get_current_authenticated_user)
):
    """Allows a connected doctor to download a patient's report."""
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can access this.")
        
    try:
        report = await reports_collection.find_one({"_id": ObjectId(report_id)})
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid Report ID format.")

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # SECURITY CHECK: Is this patient on the doctor's list?
    if report["owner_email"] not in current_user.patient_list:
        raise HTTPException(status_code=403, detail="You are not connected to this patient.")
    
    # (The rest of this code is copied from the patient's download route)
    content_id = report.get("content_id")
    if not content_id:
        raise HTTPException(status_code=400, detail="Report has no stored content ID.")

    try:
        content_doc = await report_contents_collection.find_one({"_id": ObjectId(content_id)})
        report_content = content_doc.get("content_text") if content_doc else None
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid Content ID format or DB error.")
    
    if not report_content:
        raise HTTPException(status_code=404, detail="Report content not found or is empty.")
    
    def generate_fpdf(content, filename):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf_text = content.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 10, txt=pdf_text)
        temp_pdf_path = f"temp_{filename}_{os.getpid()}.pdf"
        pdf.output(temp_pdf_path)
        return temp_pdf_path

    temp_pdf_path = await asyncio.to_thread(generate_fpdf, report_content, report_id)
    background_tasks.add_task(os.remove, temp_pdf_path)
    return FileResponse(
        temp_pdf_path,
        media_type='application/pdf',
        filename=f"{os.path.splitext(report['filename'])[0]}.pdf"
    )


@router.post("/doctor/summarize/{report_id}")
async def doctor_summarize_patient_report(
    report_id: str, 
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Summarizes the content of a SINGLE patient report.
    """
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can access this.")

    try:
        report = await reports_collection.find_one({"_id": ObjectId(report_id)})
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid Report ID format.")

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # SECURITY CHECK
    if report["owner_email"] not in current_user.patient_list:
        raise HTTPException(status_code=403, detail="You are not connected to this patient.")

    content_id_str = report.get("content_id")
    if not content_id_str:
        raise HTTPException(status_code=404, detail="Report has no content to summarize.")

    try:
        content_doc = await report_contents_collection.find_one({"_id": ObjectId(content_id_str)})
        report_content = content_doc.get("content_text") if content_doc else None
    except Exception:
        raise HTTPException(status_code=404, detail="Could not find report content.")

    if not report_content:
         return {"filename": report['filename'], "summary": "This report content is empty."}

    if not chatbot_service:
        raise HTTPException(status_code=503, detail="AI Summary service is not available.")

    # Call the new service to summarize the text
    try:
        summary = await chatbot_service.summarize_report_text(report_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating summary: {e}")

    return {"filename": report['filename'], "summary": summary}

