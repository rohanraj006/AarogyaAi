# routes/user_routes.py

from fastapi import APIRouter, HTTPException, status, Depends, Response, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from models.schemas import User, UserCreate, SESSION_COOKIE_NAME, SESSION_EXPIRATION_MINUTES 
from security import get_password_hash, verify_password, create_user_session
from database import user_collection
import random
from typing import Literal
from datetime import datetime, timezone 
from bson import ObjectId

router = APIRouter()

def generate_aarogya_id(user_type: Literal["patient", "doctor"]):
    """Generates a unique AarogyaID with a 'RI' or 'RD' prefix."""
    prefix = "RP" if user_type == "patient" else "RD"
    date_part = datetime.now().strftime("%m%d") 
    random_part = str(random.randint(100000, 999999))
    return prefix +date_part+ random_part

@router.post("/register/patient", status_code=status.HTTP_201_CREATED, tags=["Users"])
async def register_patient(
    response: Response, 
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
): 
    """Registers a new patient and logs them in immediately."""
    user = UserCreate(email=email, password=password) # Create the object from form data
    if await user_collection.find_one({"email": user.email}): 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    
    while True:
        new_id = generate_aarogya_id("patient")
        if not await user_collection.find_one({"aarogya_id": new_id}): 
            break
    
    new_user_doc_id = ObjectId()

    new_user_data = {
        "_id": new_user_doc_id,
        "email": user.email,
        "hashed_password": hashed_password,
        "aarogya_id": new_id,
        "user_type": "patient",
        "doctor_list": [],
        "patient_list": [],
        "is_public": False,
        "is_authorized": False,
    }
    
    await user_collection.insert_one(new_user_data) 

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

    # Return a simple, JSON-safe dictionary instead of a Pydantic model
    return {
        "message": "Registration successful.",
        "user_type": new_user_data["user_type"],
        "email": new_user_data["email"],
        "aarogya_id": new_user_data["aarogya_id"]
    }

@router.post("/register/doctor", status_code=status.HTTP_201_CREATED, tags=["Users"])
async def register_doctor(
    response: Response, 
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
): 
    """Registers a new doctor and logs them in immediately."""
    user = UserCreate(email=email, password=password) # Create the object from form data
    if await user_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    hashed_password = get_password_hash(user.password)
    
    while True:
        new_id = generate_aarogya_id("doctor")
        if not await user_collection.find_one({"aarogya_id": new_id}): 
            break
    
    new_user_doc_id = ObjectId()
    
    new_user_data = {
        "_id": new_user_doc_id,
        "email": user.email,
        "hashed_password": hashed_password,
        "aarogya_id": new_id,
        "user_type": "doctor",
        "is_public": False,      
        "is_authorized": False,
        "doctor_list": [], 
        "patient_list": [],
    }
    await user_collection.insert_one(new_user_data) 

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
    
    # Return a simple, JSON-safe dictionary instead of a Pydantic model
    return {
        "message": "Registration successful.",
        "user_type": new_user_data["user_type"],
        "email": new_user_data["email"],
        "aarogya_id": new_user_data["aarogya_id"]
    }

@router.post("/login", tags=["Users"])
async def login_for_access_token(
    # FIX APPLIED: Move arguments without defaults (Response, Request) to the beginning.
    response: Response, 
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """Logs in a user and sets the session cookie."""
    user_data = await user_collection.find_one({"email": form_data.username})
    
    if not user_data or not verify_password(form_data.password, user_data["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id_str = str(user_data["_id"])
    user_type = user_data["user_type"]

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

@router.post("/logout")
async def logout_user(response: Response):
    """
    Logs the user out by deleting the session cookie.
    """
    # The key is to tell the browser to delete the cookie.
    # The cookie name ('session_token') must match the one you set during login.
    response.delete_cookie(key="session_token")
    
    # You can return a success message...
    return {"message": "Successfully logged out"}