# routes/report_routes.py

import os
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from typing import List
from bson import ObjectId
from utils import extract_text_from_pdf
import chromadb
from models.schemas import User, Report
from security import get_current_user
from database import reports_collection
from ai_core.rag_engine import get_summary_response

# --- INITIALIZE THE RAG DATABASE CONNECTION ---
rag_client = chromadb.PersistentClient(path="db")
rag_collection = rag_client.get_or_create_collection(name="medical_knowledge")

router = APIRouter()
UPLOAD_DIRECTORY = "./uploads"

# --- 1. UPGRADED UPLOAD ENDPOINT ---
@router.post("/upload")
async def upload_report(
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...)
):
    """
    Uploads a report, saves it, extracts its text, and ingests it into the
    personalized knowledge base.
    """
    if not os.path.exists(UPLOAD_DIRECTORY):
        os.makedirs(UPLOAD_DIRECTORY)
        
    file_location = os.path.join(UPLOAD_DIRECTORY, f"{current_user.email}_{file.filename}")
    
    try:
        with open(file_location, "wb") as f:
            f.write(await file.read())
    except Exception:
        raise HTTPException(status_code=500, detail="Could not save file.")

    # --- NEW: TEXT EXTRACTION AND INGESTION LOGIC ---
    extracted_text = ""
    if file.content_type == 'application/pdf':
        extracted_text = extract_text_from_pdf(file_location)
    elif file.content_type == 'text/plain':
        with open(file_location, "r", encoding="utf-8") as f:
            extracted_text = f.read()

    if extracted_text:
        chunks = [chunk.strip() for chunk in extracted_text.split('\n\n') if chunk.strip()]
        if chunks:
            num_chunks = len(chunks)
            ids = [f"{current_user.email}_{file.filename}_{i}" for i in range(num_chunks)]
            # We add both owner and filename to the metadata for precise deletion later
            metadatas = [{"owner_email": current_user.email, "filename": file.filename} for _ in range(num_chunks)]

            rag_collection.add(
                ids=ids,
                documents=chunks,
                metadatas=metadatas
            )
            
    # Save the report metadata to our main MongoDB
    report_data = Report(filename=file.filename, owner_email=current_user.email)
    reports_collection.insert_one(report_data.dict())
    
    return {"message": f"Successfully uploaded and ingested {file.filename}"}

# --- 2. EXISTING "LIST MY REPORTS" ENDPOINT (No changes needed) ---
@router.get("/my-reports", response_model=List[Report])
async def get_user_reports(current_user: User = Depends(get_current_user)):
    """Retrieves a list of all reports uploaded by the currently logged-in user."""
    reports = reports_collection.find({"owner_email": current_user.email}).sort("upload_date", -1)
    report_list = []
    for report in reports:
        # This is the crucial line that converts the ObjectId to a string
        report["_id"] = str(report["_id"])
        report_list.append(Report(**report))
        
    return report_list

# --- 3. UPGRADED DELETE ENDPOINT ---
@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Deletes a report from the file system, MongoDB, and the AI's knowledge base.
    """
    report = reports_collection.find_one({"_id": ObjectId(report_id)})

    if not report or report["owner_email"] != current_user.email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    
    # Delete the physical file from the 'uploads' folder
    file_path = os.path.join(UPLOAD_DIRECTORY, f"{current_user.email}_{report['filename']}")
    if os.path.exists(file_path):
        os.remove(file_path)

    # --- NEW: Delete the report's content from the AI's knowledge base ---
    rag_collection.delete(
        where={"$and": [
            {"owner_email": current_user.email},
            {"filename": report['filename']}
        ]}
    )
    # ------------------------------------------------------------------

    # Delete the report's metadata from MongoDB
    reports_collection.delete_one({"_id": ObjectId(report_id)})
    
    return

@router.post("/{report_id}/summarize", tags=["Reports"])
async def summerize_report(
    report_id: str,
    current_user: User = Depends(get_current_user)
):
    """this finds the user report, extracts its text and returns an ai-generated summary"""
    report_meta = reports_collection.finad_one({"_id": ObjectId(report_id)})

    if not report_meta or report_meta["owner_email"] != current_user.email:
        raise HTTPException(status_code=404, detail="report not found")
    
    file_path = os.path.join(UPLOAD_DIRECTORY, f"{current_user.email}_{report_meta['filename']}")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="file not found.")
    
    extracted_text=""

    if file_path.lower().endswith('.pdf'):
        extracted_text=extract_text_from_pdf(file_path)
    elif file_path.lower().endswith('.txt'):
        with open(file_path,"r",encoding="utf-8") as f:
            extracted_text=f.read()

    if not extracted_text:
        raise HTTPException(status_code=400, detail="could not extract from report. it might be an image-only file")
    
    summary = get_summary_response(extracted_text)
    return {"filename":report_meta['filename'],"summary":summary}