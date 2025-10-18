# routes/report_routes.py
import os
import fitz # PyMuPDF
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Body
from fastapi.responses import FileResponse
from typing import List
from bson import ObjectId
from fpdf import FPDF

from models.schemas import User, Report
from security import get_current_user
from database import reports_collection, user_collection
from ai_core.rag_engine import get_summary_response, pinecone_index, embedding_model

router = APIRouter()

def ingest_text_to_pinecone(text: str, owner_email: str, filename: str):
    """Helper function to vectorize and upsert text to Pinecone."""
    if not text or not pinecone_index:
        return

    chunks = [chunk.strip() for chunk in text.split('\n\n') if chunk.strip()]
    if chunks:
        vectors = embedding_model.encode(chunks).tolist()
        metadata = [{"owner_email": owner_email, "filename": filename, "text": chunk} for chunk in chunks]
        ids = [f"{owner_email}_{filename}_{i}" for i in range(len(chunks))]
        pinecone_index.upsert(vectors=zip(ids, vectors, metadata))

@router.post("/upload")
async def upload_report(
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...)
):
    """Uploads a user's report. The file content is stored in MongoDB and vectorized into Pinecone."""
    file_content = await file.read()
    
    extracted_text = ""
    if file.content_type == 'application/pdf':
        with fitz.open(stream=file_content, filetype="pdf") as doc:
            extracted_text = "".join(page.get_text() for page in doc)
    elif file.content_type == 'text/plain':
        extracted_text = file_content.decode('utf-8')

    ingest_text_to_pinecone(extracted_text, current_user.email, file.filename)
            
    report_data = Report(
        filename=file.filename,
        owner_email=current_user.email,
        content=extracted_text 
    )
    reports_collection.insert_one(report_data.dict(by_alias=True))
    
    return {"message": f"Successfully uploaded and ingested {file.filename}."}

@router.post("/doctor/add_report")
async def doctor_add_report(
    current_user: User = Depends(get_current_user),
    patient_email: str = Body(...),
    report_content: str = Body(...),
    filename: str = Body("Doctor's Note")
):
    """Allows a connected doctor to add a new text-based report for a patient."""
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can add reports.")

    patient = user_collection.find_one({"email": patient_email})
    if not patient or patient_email not in current_user.patient_list:
        raise HTTPException(status_code=403, detail="You are not connected to this patient.")

    ingest_text_to_pinecone(report_content, patient_email, filename)
    
    report_data = Report(
        filename=filename,
        owner_email=patient_email,
        content=report_content
    )
    reports_collection.insert_one(report_data.dict(by_alias=True))

    return {"message": f"Successfully added report for {patient_email}."}


@router.get("/my-reports", response_model=List[Report])
async def get_user_reports(current_user: User = Depends(get_current_user)):
    reports = reports_collection.find({"owner_email": current_user.email}).sort("upload_date", -1)
    return [Report(**report) for report in reports]

@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(report_id: str, current_user: User = Depends(get_current_user)):
    report = reports_collection.find_one({"_id": ObjectId(report_id)})
    if not report or report["owner_email"] != current_user.email:
        raise HTTPException(status_code=404, detail="Report not found")
    
    ids_to_delete = [f"{report['owner_email']}_{report['filename']}_{i}" for i in range(100)] 
    pinecone_index.delete(ids=ids_to_delete)
    
    reports_collection.delete_one({"_id": ObjectId(report_id)})
    return

@router.get("/{report_id}/download")
async def download_report_as_pdf(report_id: str, current_user: User = Depends(get_current_user)):
    report = reports_collection.find_one({"_id": ObjectId(report_id)})
    if not report or report["owner_email"] != current_user.email:
        raise HTTPException(status_code=404, detail="Report not found")
        
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # FPDF requires UTF-8 text to be encoded properly
    pdf_text = report.get("content", "No content found.").encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 10, txt=pdf_text)
    
    temp_pdf_path = f"temp_{report_id}.pdf"
    pdf.output(temp_pdf_path)
    
    # Return the file and FastAPI will handle cleanup
    return FileResponse(
        temp_pdf_path,
        media_type='application/pdf',
        filename=f"{os.path.splitext(report['filename'])[0]}.pdf"
    )

@router.post("/{report_id}/summarize")
async def summarize_report(report_id: str, current_user: User = Depends(get_current_user)):
    report = reports_collection.find_one({"_id": ObjectId(report_id)})
    if not report or report["owner_email"] != current_user.email:
        raise HTTPException(status_code=404, detail="Report not found")
    
    report_content = report.get("content")
    if not report_content:
        raise HTTPException(status_code=400, detail="Report has no text content to summarize.")
    
    summary = get_summary_response(report_content)
    return {"filename": report['filename'], "summary": summary}