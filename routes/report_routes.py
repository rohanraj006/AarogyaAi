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

# --- Improved Chunking Helper Function ---
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
        
        # Move start position back by overlap size for next chunk
        start += chunk_size - chunk_overlap
    
    return chunks

# --- Helper function for Pinecone ingestion, now using better chunking ---
def ingest_text_to_pinecone(text: str, owner_email: str, filename: str):
    """Helper function to vectorize and upsert text to Pinecone."""
    if not text or not pinecone_index:
        return

    # Using the more robust chunking strategy
    chunks = get_chunks_with_overlap(text) 
    
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
            
    # Note: 'content' is not in your Pydantic Report schema, but it's used here and stored.
    report_data = Report(
        filename=file.filename,
        owner_email=current_user.email,
    )
    # Storing content in the MongoDB document directly, as done originally
    doc_to_insert = report_data.dict(by_alias=True)
    doc_to_insert["content"] = extracted_text 
    reports_collection.insert_one(doc_to_insert)
    
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
    
    if current_user.user_type == "doctor" and not current_user.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be authorized by the platform owner to use the AI summarization feature."
        )

    patient = user_collection.find_one({"email": patient_email})
    if not patient or patient_email not in current_user.patient_list:
        raise HTTPException(status_code=403, detail="You are not connected to this patient.")

    ingest_text_to_pinecone(report_content, patient_email, filename)
    
    report_data = Report(
        filename=filename,
        owner_email=patient_email,
    )
    doc_to_insert = report_data.dict(by_alias=True)
    doc_to_insert["content"] = report_content 
    reports_collection.insert_one(doc_to_insert)

    return {"message": f"Successfully added report for {patient_email}."}


@router.get("/my-reports", response_model=List[Report])
async def get_user_reports(current_user: User = Depends(get_current_user)):
    """
    Retrieves all reports for the current user, fixing the ObjectId to string conversion.
    """
    reports_cursor = reports_collection.find({"owner_email": current_user.email}).sort("upload_date", -1)
    
    # FIX: Convert MongoDB's ObjectId to a string and assign it to the 'id' field
    return [
        Report(**{**report, "id": str(report["_id"])}) 
        for report in reports_cursor
    ]

@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(report_id: str, current_user: User = Depends(get_current_user)):
    """
    Deletes a report and all its associated vectors from Pinecone using a metadata filter.
    """
    report = reports_collection.find_one({"_id": ObjectId(report_id)})
    if not report or report["owner_email"] != current_user.email:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # EFFICIENT AND ACCURATE FIX: Delete by metadata filter
    if pinecone_index:
        pinecone_index.delete(
            filter={
                "owner_email": report['owner_email'],
                "filename": report['filename']
            }
        )
    
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
    
    if current_user.user_type == "doctor" and not current_user.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be authorized by the platform owner to use the AI summarization feature."
        )
    
    report_content = report.get("content")
    if not report_content:
        raise HTTPException(status_code=400, detail="Report has no text content to summarize.")
    
    summary = get_summary_response(report_content)
    return {"filename": report['filename'], "summary": summary}