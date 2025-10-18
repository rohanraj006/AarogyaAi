from fastapi import APIRouter, Depends, HTTPException, status, Query
from models.schemas import User
from security import get_current_user
from database import user_collection

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