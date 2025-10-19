# routes/admin_routes.py

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Body
from database import user_collection
from models.schemas import User, DoctorInfo
from security import get_current_user # Used for authentication (not admin role enforcement)

router = APIRouter()

# NOTE: These endpoints currently lack robust "admin" role protection.
# They will need a true admin authentication check in a future step.

@router.post("/authorize/doctor/{doctor_email}", tags=["Admin"])
async def authorize_doctor(
    doctor_email: str,
    # current_user: User = Depends(get_current_user) # Placeholder for admin check
):
    """Manually authorizes a doctor, granting them access to core features (like patient queue and public listing)."""
    
    # 1. Find the doctor and ensure they exist and are, in fact, a doctor
    result = user_collection.find_one_and_update(
        {"email": doctor_email, "user_type": "doctor"},
        {"$set": {"is_authorized": True}},
        # return_document=True is good practice but not strictly required here
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Doctor not found or email is not associated with a doctor account.")
    
    return {"message": f"Doctor {doctor_email} is now fully authorized."}


@router.get("/unauthorized_doctors", response_model=List[DoctorInfo], tags=["Admin"])
async def get_unauthorized_doctors():
    """Retrieves a list of doctors waiting for authorization."""
    
    doctors_cursor = user_collection.find({
        "user_type": "doctor", 
        "is_authorized": False
    })
    
    # Map the results to the DoctorInfo schema
    return [
        DoctorInfo(
            email=doc["email"], 
            aarogya_id=doc["aarogya_id"],
            is_public=doc.get("is_public", False), 
            is_authorized=doc.get("is_authorized", False)
        ) 
        for doc in doctors_cursor
    ]