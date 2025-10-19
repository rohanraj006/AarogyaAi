# routes/user_routes.py

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from grpc import Status
from models.schemas import User, UserCreate
from security import get_password_hash, verify_password, create_user_session, SESSION_COOKIE_NAME, SESSION_EXPIRATION_MINUTES # Added session imports, Removed create_access_token
from database import user_collection
import random
from typing import Literal
from datetime import datetime, timezone # Added timezone
from bson import ObjectId

router = APIRouter()

def generate_aarogya_id(user_type: Literal["patient", "doctor"]):
    """Generates a unique AarogyaID with a 'RI' or 'RD' prefix."""
    prefix = "RP" if user_type == "patient" else "RD"
    date_part = datetime.datetime.now().strftime("%m%d") 
    random_part = str(random.randint(100000, 999999))
    return prefix +date_part+ random_part

@router.post("/register/patient", response_model=User, status_code=Status.HTTP_201_CREATED, tags=["Users"])
async def register_patient(user: UserCreate, response: Response, request: Request): # Added response, request
    """Registers a new patient and logs them in immediately."""
    if await user_collection.find_one({"email": user.email}): # Use await for Motor
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    
    while True:
        new_id = generate_aarogya_id("patient")
        if not await user_collection.find_one({"aarogya_id": new_id}): # Use await for Motor
            break
    
    # Use ObjectId() for the document ID, as expected by the new session system
    new_user_doc_id = ObjectId()

    new_user_data = {
        "_id": new_user_doc_id, # Add MongoDB ID
        "email": user.email,
        "hashed_password": hashed_password,
        "aarogya_id": new_id,
        "user_type": "patient",
        "doctor_list": [], # Initialize for Pydantic schema
        "patient_list": [],
        "is_public": False,
        "is_authorized": False,
    }
    
    await user_collection.insert_one(new_user_data) # Use await for Motor

    # --- NEW: Create Session and Set Cookie ---
    user_id_str = str(new_user_doc_id)
    session_token = await create_user_session(user_id=user_id_str, user_type="patient")
    
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        max_age=SESSION_EXPIRATION_MINUTES * 60,
        path="/",
        secure=request.url.scheme == "https",
        samesite="Lax"
    )
    # --- END NEW ---

    return new_user_data

@router.post("/register/doctor", response_model=User, status_code=Status.HTTP_201_CREATED, tags=["Users"])
async def register_doctor(user: UserCreate, response: Response, request: Request): # Added response, request
    """Registers a new doctor and logs them in immediately."""
    if await user_collection.find_one({"email": user.email}): # Use await for Motor
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user.password)
    
    while True:
        new_id = generate_aarogya_id("doctor")
        if not await user_collection.find_one({"aarogya_id": new_id}): # Use await for Motor
            break
    
    # Use ObjectId() for the document ID
    new_user_doc_id = ObjectId()
    
    new_user_data = {
        "_id": new_user_doc_id, # Add MongoDB ID
        "email": user.email,
        "hashed_password": hashed_password,
        "aarogya_id": new_id,
        "user_type": "doctor",
        "is_public": False,      
        "is_authorized": False,
        "doctor_list": [], # Initialize for Pydantic schema
        "patient_list": [],
    }
    await user_collection.insert_one(new_user_data) # Use await for Motor

    # --- NEW: Create Session and Set Cookie ---
    user_id_str = str(new_user_doc_id)
    session_token = await create_user_session(user_id=user_id_str, user_type="doctor")
    
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        max_age=SESSION_EXPIRATION_MINUTES * 60,
        path="/",
        secure=request.url.scheme == "https",
        samesite="Lax"
    )
    # --- END NEW ---
    
    return new_user_data

@router.post("/login", tags=["Users"])
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    response: Response = Response(), # Added response
    request: Request = Request() # Added request
):
    user_data = await user_collection.find_one({"email": form_data.username}) # Use await for Motor
    
    if not user_data or not verify_password(form_data.password, user_data["hashed_password"]):
        raise HTTPException(
            status_code=Status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id_str = str(user_data["_id"])
    user_type = user_data["user_type"]

    # --- NEW: Create Session and Set Cookie (replaces JWT) ---
    session_token = await create_user_session(user_id=user_id_str, user_type=user_type)
    
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        max_age=SESSION_EXPIRATION_MINUTES * 60,
        path="/",
        secure=request.url.scheme == "https",
        samesite="Lax"
    )
    
    return {
        "message": "Login successful. Session cookie set.", 
        "user_type": user_type,
        "is_authorized": user_data.get("is_authorized", False)
    }