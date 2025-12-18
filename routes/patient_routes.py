# routes/patient_routes.py

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

# Security & Database
from security import get_current_authenticated_user
from models.schemas import User
from database import db

# AI Core
from ai_core.chatbot_service import MedicalChatbot
from ai_core.helpers import fetch_patient_context

router = APIRouter()
templates = Jinja2Templates(directory="templates")
chatbot = MedicalChatbot()

@router.get("/wellness", response_class=HTMLResponse)
async def get_wellness_plan(
    request: Request,
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Generates a personalized wellness plan for the authenticated patient using AI.
    """
    if current_user.user_type != "patient":
        raise HTTPException(status_code=403, detail="Access denied. Only patients can access the wellness plan.")

    # 1. Fetch Patient Context (Profile + Medical Record)
    context_data = await fetch_patient_context(current_user.email)
    
    # 2. Generate Plan using Chatbot Service
    # We use the new method added to chatbot_service
    wellness_plan_raw = await chatbot.generate_wellness_plan(context_data)

    # 3. Parse the Raw Text into Sections for the Template
    # The prompt explicitly asks for specific headers ("Diet Recommendations:", etc.)
    sections = {
        "diet": "No specific recommendations available.",
        "habits": "No specific recommendations available.",
        "avoid": "No specific recommendations available.",
        "exercise": "No specific recommendations available."
    }

    current_section = None
    lines = wellness_plan_raw.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Simple keyword matching based on the prompt's headers
        if "Diet Recommendations" in line:
            current_section = "diet"
            sections[current_section] = "" # Clear default
        elif "Healthy Habits" in line:
            current_section = "habits"
            sections[current_section] = ""
        elif "Things to Avoid" in line:
            current_section = "avoid"
            sections[current_section] = ""
        elif "Exercise Plan" in line:
            current_section = "exercise"
            sections[current_section] = ""
        elif current_section:
            # Append content to the current section
            sections[current_section] += line + " "

    return templates.TemplateResponse(
        "wellness.html",
        {
            "request": request,
            "user": current_user,
            "wellness_plan": sections,
            "datetime_cls": datetime
        }
    )


@router.post("/patient/emergency/alert")
async def alert_doctor(
    request: Request, 
    current_user: User = Depends(get_current_authenticated_user)
):
    try:
        body = await request.json()
        location = body.get("location", "GPS Unavailable")
    except Exception:
        location = "GPS Unavailable"

    mapping = db.doctor_patient_mappings.find_one({
        "patient_email": current_user.email
    })

    doctor_info = "108 (Ambulance)"

    if mapping:
        doctor_email = mapping.get("doctor_email")
        doctor_doc = db.users.find_one({"email": doctor_email})
        
        if doctor_doc:
            doctor_name = doctor_doc.get("name", {}).get("first", "Doctor")
            doctor_phone = doctor_doc.get("phone", "")
            doctor_info = f"Dr. {doctor_name}"
            
            print(f"🚨 EMERGENCY: Patient {current_user.email} @ {location}")
            print(f"📨 ALERTING: {doctor_info} on {doctor_phone}")

    return {
        "status": "alert_sent", 
        "notified": doctor_info,
        "timestamp": datetime.utcnow().isoformat()
    }