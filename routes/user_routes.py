# routes/user_routes.py

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from models.schemas import User, UserCreate
from security import get_password_hash, verify_password, create_access_token
from database import user_collection
import random
from typing import Literal
import datetime

router = APIRouter()

def generate_aarogya_id(user_type: Literal["patient", "doctor"]):
    """Generates a unique AarogyaID with a 'RI' or 'RD' prefix."""
    prefix = "RP" if user_type == "patient" else "RD"
    date_part = datetime.datetime.now().strftime("%m%d") 
    random_part = str(random.randint(100000, 999999))
    return prefix +date_part+ random_part

@router.post("/register/patient", response_model=User, status_code=status.HTTP_201_CREATED, tags=["Users"])
async def register_patient(user: UserCreate):
    """Registers a new patient with a guaranteed unique 'RP' prefixed AarogyaID."""
    if user_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    
    # --- THIS IS THE GUARANTEED UNIQUENESS CHECK ---
    while True:
        new_id = generate_aarogya_id("patient")
        if not user_collection.find_one({"aarogya_id": new_id}):
            break # Exit the loop if the ID is unique
    # -----------------------------------------------
    
    new_user_data = {
        "email": user.email,
        "hashed_password": hashed_password,
        "aarogya_id": new_id,
        "user_type": "patient"
    }
    user_collection.insert_one(new_user_data)
    return new_user_data

@router.post("/register/doctor", response_model=User, status_code=status.HTTP_201_CREATED, tags=["Users"])
async def register_doctor(user: UserCreate):
    """Registers a new doctor with a guaranteed unique 'RD' prefixed AarogyaID."""
    if user_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user.password)
    
    # --- THIS IS THE GUARANTEED UNIQUENESS CHECK ---
    while True:
        new_id = generate_aarogya_id("doctor")
        if not user_collection.find_one({"aarogya_id": new_id}):
            break # Exit the loop if the ID is unique
    # -----------------------------------------------
    
    new_user_data = {
        "email": user.email,
        "hashed_password": hashed_password,
        "aarogya_id": new_id,
        "user_type": "doctor",
        "is_public": False,      
        "is_authorized": False
    }
    user_collection.insert_one(new_user_data)
    return new_user_data

@router.post("/login", tags=["Users"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user_data = user_collection.find_one({"email": form_data.username})
    if not user_data or not verify_password(form_data.password, user_data["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = {"sub": user_data["email"]}
    
    # NEW LOGIC: Include is_authorized status in the token for all subsequent checks
    if user_data.get("user_type") == "doctor":
        is_authorized = user_data.get("is_authorized", False)
        
        # We include the flag in the token
        token_data["is_authorized"] = is_authorized
        
        # Optional: You can choose to provide a warning/message here, 
        # but the actual feature blocking will happen in the appointment routes.
        # if not is_authorized:
        #     # You can add a response key here to inform the client
        #     pass

    access_token = create_access_token(data=token_data)
    return {"access_token": access_token, "token_type": "bearer"}