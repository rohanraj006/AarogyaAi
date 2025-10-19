from fastapi import APIRouter, Body, Depends, HTTPException, status, Query, Body
from models.schemas import DictationSaveBody, MedicalRecord, User, Diagnosis, Medication
from security import get_current_user
from database import user_collection, medical_records_collection
from ai_core.rag_engine import process_dictation 
from pydantic import ValidationError
from typing import List, Dict,  Any

router = APIRouter()

@router.get("/patients/search")
async def search_for_patient(
    current_user: User = Depends(get_current_user),
    aarogya_id: str = Query(..., min_length=10, max_length=15)
):
    """allows loggedin doctor to search a patient by their aarogyaid, returns basic
    non sensitive info if not found"""

    if current_user.user_type != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access denied. ONly doctors can search for patients."
        )
    
    if not current_user.is_authorized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be authorized by the platform owner to access patient features."
            )

    patient = user_collection.find_one({
        "aarogya_id": aarogya_id,
        "user_type":"patient"
    })
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no patient found with aarogyaID: {aarogya_id}"
        )
    
    return{
        "aarogya_id":patient["aarogya_id"],
        "email":patient["email"]
    }

@router.post("/toggle_public", tags=["Doctor"])
async def doctor_toggle_public_status(
    current_user: User = Depends(get_current_user), 
    is_public: bool = Body(..., embed=True)
):
    """Allows an authorized doctor to set their profile visibility for the public directory."""
    
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only doctors can manage their public status.")
    
    # Enforce Authorization Gate: Only authorized doctors can be public
    if not current_user.is_authorized:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be authorized by the platform owner to be listed publicly.")

    # Update the doctor's document in the database
    user_collection.update_one(
        {"email": current_user.email},
        {"$set": {"is_public": is_public}}
    )
    
    return {"message": f"Your public status has been set to {is_public}."}

@router.post("/dictation/process", response_model=MedicalRecord, tags=["Doctor"])
async def process_dictation_notes(
    dictation_text: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user)
):
    """
    Receives raw dictated text from a doctor and uses AI to convert it into 
    structured MedicalRecord data (Diagnosis and Medication lists).
    """
    
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only doctors can process dictation notes.")
    
    # SECURITY CHECK: Block unauthorized doctors
    if not current_user.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be authorized by the platform owner to use AI dictation."
        )

    if not dictation_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dictation text cannot be empty.")

    # 1. Send the text to the AI core for structured extraction
    structured_data = process_dictation(dictation_text)

    if not structured_data or structured_data.get("error"):
        # Handle case where AI fails or returns an error message
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=structured_data.get("error", "AI failed to process notes. Please check the dictation or try again.")
        )

    # 2. Validate the AI's output against the Pydantic schemas
    try:
        # Pydantic validation ensures the AI output is clean and safe
        validated_record = MedicalRecord(**structured_data)
        
        # 3. Return the clean, validated structured data to the front end
        return validated_record
        
    except ValidationError as e:
        # This catches cases where the AI outputted invalid JSON or incorrect fields
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI output validation failed. Data integrity error: {e.errors()}"
        )
    
@router.post("/patient/records/save", status_code=status.HTTP_200_OK, tags=["Doctor"])
async def save_structured_medical_data(
    body: DictationSaveBody,
    current_user: User = Depends(get_current_user)
):
    """
    Saves new diagnosis/medication data (typically from the AI dictation feature) 
    to the connected patient's structured medical record.
    """
    if current_user.user_type != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only doctors can update patient records.")
    
    # 1. Authorization Check
    if not current_user.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be authorized by the platform owner to update patient records."
        )

    # 2. Connection Check: Ensure the doctor is connected to this patient
    if body.patient_email not in current_user.patient_list:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Patient is not connected to your account.")
        
    
    # 3. Persistence Logic: Append new entries to the dedicated medical records collection.
    
    # We will append each new diagnosis and medication to the existing record.
    # Find the patient's current record or prepare to create a new one.
    existing_record = medical_records_collection.find_one({"owner_email": body.patient_email})
    
    # Convert Pydantic objects to dicts for MongoDB storage
    new_diagnoses = [d.dict() for d in body.medical_record.diagnosis]
    new_medications = [m.dict() for m in body.medical_record.medications]

    if existing_record:
        # Use $push with $each to append all new entries to existing lists
        medical_records_collection.update_one(
            {"owner_email": body.patient_email},
            {
                "$push": {
                    "diagnosis": {"$each": new_diagnoses},
                    "medications": {"$each": new_medications}
                }
            }
        )
    else:
        # Create a new document for the patient
        new_record = {
            "owner_email": body.patient_email,
            "diagnosis": new_diagnoses,
            "medications": new_medications
        }
        medical_records_collection.insert_one(new_record)
        
    return {"message": f"Successfully updated structured medical record for {body.patient_email}."}