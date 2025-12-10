# routes/ai_routes.py

from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from typing import Optional
from bson import ObjectId

# Security & Database
from security import get_current_authenticated_user
from models.schemas import User, ChatMessage
from database import chat_messages_collection, user_collection

# AI Core
from ai_core.chatbot_service import MedicalChatbot
from ai_core.helpers import fetch_patient_context

router = APIRouter()
templates = Jinja2Templates(directory="templates")
chatbot = MedicalChatbot()

@router.get("/consultation", response_class=HTMLResponse)
async def get_ai_consultation_page(
    request: Request,
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Renders the Command Center.
    Pre-fetches the patient list for the dropdown.
    """
    patients = []
    if current_user.user_type == "doctor" and current_user.patient_list:
        patients_cursor = user_collection.find({
            "email": {"$in": current_user.patient_list},
            "user_type": "patient"
        })
        patients = await patients_cursor.to_list(length=None)

    return templates.TemplateResponse("ai_consultation.html", {
        "request": request,
        "user": current_user,
        "user_json": current_user.model_dump_json(by_alias=True),
        "datetime_cls": datetime,
        "patients": patients
    })

@router.post("/chat", response_class=HTMLResponse)
async def chat_endpoint(
    request: Request,
    query: str = Form(...), 
    action: str = Form("ask"),
    patient_id: Optional[str] = Form(None), 
    current_user: User = Depends(get_current_authenticated_user)
):
    ai_response_text = "Sorry, I could not process that request."
    query_to_save = query
    target_email = current_user.email 
    context_patient_id = None 

    try:
        # 1. Resolve Patient Context if ID provided
        if current_user.user_type == "doctor" and patient_id:
            try:
                patient = await user_collection.find_one({"_id": ObjectId(patient_id)})
                if patient and patient["email"] in current_user.patient_list:
                    target_email = patient["email"]
                    context_patient_id = patient_id # TAG THE CHAT
                    query_to_save = f"[Patient: {patient.get('name', {}).get('first', 'Unknown')}] {query}"
            except Exception as e:
                print(f"Error resolving patient ID: {e}")

        # 2. Generate Response
        context = await fetch_patient_context(target_email)
        
        if action == 'summarize':
             ai_response_text = await chatbot.summarize_medical_record(context)
             query_to_save = f"[Summary Request] {query_to_save}"
        else:
             asking_user_dict = current_user.model_dump(by_alias=True)
             ai_response_text = await chatbot.generate_response(context, query, asking_user_dict)
        
        # 3. Save to DB with Tag
        chat_message = ChatMessage(
            owner_email=current_user.email,
            user_query=query_to_save,
            ai_response=ai_response_text,
            patient_id=context_patient_id # Save the tag (or None)
        )
        await chat_messages_collection.insert_one(chat_message.model_dump())

        # 4. Return HTML
        return HTMLResponse(f"""
        <div class="flex flex-col space-y-4 mb-6 animate-fade-in">
            <div class="self-start bg-white border border-gray-100 text-gray-800 px-5 py-3 rounded-2xl rounded-tl-none max-w-[85%] shadow-sm">
                <div class="flex items-center gap-2 mb-1">
                    <span class="text-xs font-bold text-indigo-600 uppercase tracking-wider">Aarogya AI</span>
                </div>
                <div class="prose prose-sm text-gray-700 leading-relaxed max-w-none">
                    {ai_response_text.replace('\n', '<br>')}
                </div>
            </div>
        </div>
        """)
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-50 text-red-600 rounded-lg text-sm text-center">Error: {str(e)}</div>')

@router.get("/chat/history", response_class=HTMLResponse)
async def get_chat_history(
    patient_id: Optional[str] = Query(None), 
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Logic:
    - Doctor + patient_id -> Show history for that patient.
    - Doctor + NO patient_id -> Show ONLY untagged history (General).
    - Patient -> Show their own history.
    """
    query = {"owner_email": current_user.email}
    
    if current_user.user_type == "doctor":
        # Strict filtering: If no ID sent, strictly find records where patient_id IS NULL
        query["patient_id"] = patient_id 
         
    history_cursor = chat_messages_collection.find(query).sort("timestamp", 1)
    history_list = await history_cursor.to_list(length=50)
    
    if not history_list:
        return HTMLResponse('<div class="text-center text-gray-400 text-sm mt-10">No history found.</div>')

    html_content = ""
    for msg in history_list:
        html_content += f"""
        <div class="flex flex-col space-y-4 mb-6">
            <div class="self-end bg-indigo-600 text-white px-5 py-3 rounded-2xl rounded-tr-none max-w-[80%] shadow-md">
                <p class="text-sm">{msg.get('user_query')}</p>
            </div>
            <div class="self-start bg-white border border-gray-100 text-gray-800 px-5 py-3 rounded-2xl rounded-tl-none max-w-[85%] shadow-sm">
                <div class="prose prose-sm text-gray-700 leading-relaxed max-w-none">
                    {msg.get('ai_response', '').replace('\n', '<br>')}
                </div>
            </div>
        </div>
        """
    return HTMLResponse(html_content)