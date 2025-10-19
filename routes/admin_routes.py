# routes/admin_routes.py

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from database import user_collection # Motor collection
from models.schemas import User, DoctorInfo
from security import get_current_authenticated_user # UPDATED IMPORT

router = APIRouter()

# NOTE: These endpoints still lack robust "admin" role protection.

@router.post("/authorize/doctor/{doctor_email}", tags=["Admin"])
async def authorize_doctor(
    doctor_email: str,
    # current_user: User = Depends(get_current_authenticated_user) # Placeholder for admin check
):
    """Manually authorizes a doctor, granting them access to core features."""
    
    # 1. Find the doctor and ensure they exist and are, in fact, a doctor
    # Use await for Motor
    result = await user_collection.find_one_and_update(
        {"email": doctor_email, "user_type": "doctor"},
        {"$set": {"is_authorized": True}},
        # return_document=True is good practice but Motor returns a document or None
    )
    
   
    if not result:
        existing_doc = await user_collection.find_one({"email": doctor_email, "user_type": "doctor"})
        if not existing_doc:
             raise HTTPException(status_code=404, detail="Doctor not found or email is not associated with a doctor account.")

        # If it was a doctor, proceed with update_one (which returns an UpdateResult object)
        update_result = await user_collection.update_one(
            {"email": doctor_email, "user_type": "doctor"},
            {"$set": {"is_authorized": True}}
        )
        if update_result.matched_count == 0:
             raise HTTPException(status_code=404, detail="Doctor not found or email is not associated with a doctor account.")

    return {"message": f"Doctor {doctor_email} is now fully authorized."}


@router.get("/unauthorized_doctors", response_model=List[DoctorInfo], tags=["Admin"])
async def get_unauthorized_doctors():
    """Retrieves a list of doctors waiting for authorization."""
    
    doctors_cursor = user_collection.find({
        "user_type": "doctor", 
        "is_authorized": False
    })
    
    # Use await for Motor and to_list
    doctors_list = await doctors_cursor.to_list(length=1000)
    
    # Map the results to the DoctorInfo schema
    return [
        DoctorInfo(
            email=doc["email"], 
            aarogya_id=doc["aarogya_id"],
            is_public=doc.get("is_public", False), 
            is_authorized=doc.get("is_authorized", False)
        ) 
        for doc in doctors_list
    ]