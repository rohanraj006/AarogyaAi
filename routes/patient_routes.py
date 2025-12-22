# routes/patient_routes.py

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

# Security & Database
from security import get_current_authenticated_user
from models.schemas import User
from database import db, user_collection, instant_meetings_collection,notifications_collection

# AI Core
from ai_core.chatbot_service import MedicalChatbot
from ai_core.helpers import fetch_patient_context
from app.services.google_service import create_google_meet_link

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


@router.post("/emergency/alert")
async def alert_doctor(
    request: Request, 
    current_user: User = Depends(get_current_authenticated_user)
):
    # 1. Generate Emergency Google Meet Link (SYNCHRONOUS CALL)
    # We remove 'await' because the function in google_service.py is not async
    meet_link = create_google_meet_link(
        summary=f"🚨 SOS EMERGENCY: {current_user.name.first} {current_user.name.last}",
        start_time=datetime.utcnow(),
        attendee_emails=[current_user.email]
    )

    # 2. Find a Responder (Registered Doctor or General Physician)
    # We prioritize doctors in the patient's existing list who are 'available'
    matched_responder = await user_collection.find_one({
        "user_type": "doctor",
        "availability_status": "available",
        "email": {"$in": current_user.doctor_list if current_user.doctor_list else []}
    })

    # If no registered doctor is online, find any available General Physician/Paramedic
    if not matched_responder:
        matched_responder = await user_collection.find_one({
            "user_type": "doctor",
            "availability_status": "available",
            "specialization": {"$regex": "General|Paramedic", "$options": "i"}
        })

    if matched_responder:
        # Create an auto-accepted record so the doctor's dashboard can pop up the alert
        emergency_request = {
            "patient_id": str(current_user.id),
            "doctor_id": str(matched_responder["_id"]),
            "patient_name": f"{current_user.name.first} {current_user.name.last}",
            "status": "accepted", # Pre-accepted for SOS
            "meet_link": meet_link,
            "created_at": datetime.utcnow(),
            "type": "emergency"
        }
        await instant_meetings_collection.insert_one(emergency_request)
        notification_entry = {
            "user_id": str(matched_responder["_id"]),
            "type": "emergency",
            "title": "🚨 EMERGENCY SOS",
            "message": f"Patient {current_user.name.first} has triggered an SOS. Location: GPS Unavailable.",
            "link": meet_link,
            "timestamp": datetime.utcnow(),
            "is_read": False
        }
        await notifications_collection.insert_one(notification_entry) #

    return {
        "status": "emergency_protocol_initiated",
        "meet_link": meet_link,
        "responder_found": True if matched_responder else False
    }

