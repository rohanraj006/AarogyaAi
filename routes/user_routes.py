# routes/user_routes.py

from fastapi import APIRouter, HTTPException, status, Depends, Response, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from models.schemas import User, UserCreate, SESSION_COOKIE_NAME, SESSION_EXPIRATION_MINUTES 
from security import get_password_hash, verify_password, create_user_session, get_current_authenticated_user
from database import user_collection
import random
from typing import Literal, Optional
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
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone_number: str = Form(...),
    age: int = Form(...),
    gender: str = Form(...),
    street: str = Form(...),
    city: str = Form(...),
    state: str = Form(...),
    zip_code: str = Form(...),
    country: str = Form(...),
    blood_group: str = Form(...),
    emergency_name: str = Form(...),
    emergency_phone: str = Form(...),
    emergency_relation: str = Form(...),
    medical_conditions: Optional[str] = Form(None),
    allergies: Optional[str] = Form(None),
    current_medications: Optional[str] = Form(None)
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
    name_obj = {"first": first_name, "last": last_name}
    address_obj = {"street": street, "city": city, "state": state, "zip": zip_code, "country": country}
    emergency_obj = {
        "name": emergency_name,
        "phone": emergency_phone,
        "relationship": emergency_relation
    }

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
        "name": name_obj,
        "phone_number": phone_number,
        "age": age,
        "gender": gender,
        "address": address_obj,
        "blood_group": blood_group,     
        "emergency_contact": emergency_obj,
        "medical_conditions": medical_conditions or "",
        "allergies": allergies or "",
        "current_medications": current_medications or "",
        "registration_date": datetime.now(timezone.utc)
    }
    
    await user_collection.insert_one(new_user_data) 

    user_id_str = str(new_user_doc_id)
    session_token = await create_user_session(user_id=user_id_str, user_type="patient")
    
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        max_age=SESSION_EXPIRATION_MINUTES * 30,
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
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone_number: str = Form(...),
    specialization: str = Form(...),
    blood_group: str = Form(...),
    age: int = Form(...),
    gender: str = Form(...),
    emergency_name: str = Form(...),
    emergency_phone: str = Form(...),
    emergency_relation: str = Form(...),
    street: str = Form(...),
    city: str = Form(...),
    state: str = Form(...),
    zip_code: str = Form(...),
    country: str = Form(...)
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
    name_obj = {"first": first_name, "last": last_name}
    emergency_obj = {
        "name": emergency_name,
        "phone": emergency_phone,
        "relationship": emergency_relation
    }
    address_obj = {
        "street": street,
        "city": city, 
        "state": state, 
        "zip": zip_code, 
        "country": country
    }
    
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
        "name": name_obj,
        "phone_number": phone_number,
        "age": age,               
        "gender": gender,         
        "address": address_obj,   
        "blood_group": blood_group,    
        "emergency_contact": emergency_obj,
        "specialization": specialization,
        "registration_date": datetime.now(timezone.utc)
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

# In routes/user_routes.py

@router.post("/update_profile", tags=["Users"])
async def update_user_profile(
    current_user: User = Depends(get_current_authenticated_user),
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone_number: str = Form(...),
    # Optional fields
    age: Optional[int] = Form(None),
    gender: Optional[str] = Form(None),
    blood_group: Optional[str] = Form(None), # <--- NEW
    street: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    zip_code: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    # Emergency Contact Fields
    emergency_name: Optional[str] = Form(None), # <--- NEW
    emergency_phone: Optional[str] = Form(None), # <--- NEW
    emergency_relation: Optional[str] = Form(None),
    medical_conditions: Optional[str] = Form(None),
    allergies: Optional[str] = Form(None),
    current_medications: Optional[str] = Form(None),
    specialization: Optional[str] = Form(None)
):
    """Updates profile with medical and emergency info."""
    
    print(f"DEBUG: Received update for {current_user.email}")
    
    name_obj = {"first": first_name, "last": last_name}
    
    update_data = {
        "name": name_obj,
        "phone_number": phone_number
    }

    if current_user.user_type == "patient":
        if age: update_data["age"] = age
        if gender: update_data["gender"] = gender
        if blood_group: update_data["blood_group"] = blood_group # <--- Update Blood Group
        if medical_conditions is not None: update_data["medical_conditions"] = medical_conditions
        if allergies is not None: update_data["allergies"] = allergies
        if current_medications is not None: update_data["current_medications"] = current_medications

        if street or city or state or zip_code or country:
            address_obj = {
                "street": street or "",
                "city": city or "",
                "state": state or "",
                "zip": zip_code or "",
                "country": country or ""
            }
            update_data["address"] = address_obj
        
        # Handle Emergency Contact Update
        if emergency_name or emergency_phone or emergency_relation:
            emergency_obj = {
                "name": emergency_name or "",
                "phone": emergency_phone or "",
                "relationship": emergency_relation or ""
            }
            update_data["emergency_contact"] = emergency_obj

    elif current_user.user_type == "doctor":
        if specialization:
            update_data["specialization"] = specialization

    from bson import ObjectId
    result = await user_collection.update_one(
        {"_id": ObjectId(current_user.id)},
        {"$set": update_data}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")

    return {"message": "Profile updated successfully."}


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