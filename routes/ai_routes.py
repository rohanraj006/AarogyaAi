# routes/ai_routes.py

from fastapi import APIRouter, Depends, HTTPException, Request, Form
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
    Renders the dedicated AI Consultation page (Full Screen Chat).
    Fetches patient list if the user is a doctor.
    """
    patients = []
    if current_user.user_type == "doctor" and current_user.patient_list:
        # Fetch connected patients for the dropdown
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
    """
    Handles chat interactions.
    RETURNS ONLY THE AI RESPONSE HTML to allow for optimistic UI updates on the client.
    """
    ai_response_text = "Sorry, I could not process that request."
    query_to_save = query
    target_email = current_user.email 

    try:
        # --- Doctor Context Switching Logic ---
        if current_user.user_type == "doctor" and patient_id:
            try:
                patient = await user_collection.find_one({"_id": ObjectId(patient_id)})
                if patient:
                    if patient["email"] in current_user.patient_list:
                        target_email = patient["email"]
                        query_to_save = f"[Patient: {patient.get('name', {}).get('first', 'Unknown')}] {query}"
                    else:
                        return HTMLResponse('<div class="p-3 bg-red-50 text-red-600 rounded-lg text-sm">Error: Not connected to patient.</div>')
            except Exception as e:
                print(f"Error resolving patient ID: {e}")
        # --------------------------------------

        # 1. Fetch Context of the Target (Patient)
        context = await fetch_patient_context(target_email)

        # 2. Process Intent
        if action == 'summarize':
            target_user_type = context.get('user_doc', {}).get('user_type')
            if target_user_type != 'patient':
                 return HTMLResponse('<div class="text-xs text-red-500 p-2 text-center">Summary is only available for patient records.</div>')
            
            ai_response_text = await chatbot.summarize_medical_record(context)
            query_to_save = f"[Summary Request] {query_to_save}"
        
        elif action == 'ask':
            # --- MODIFIED: Pass current_user dict to generate_response ---
            asking_user_dict = current_user.model_dump(by_alias=True)
            ai_response_text = await chatbot.generate_response(context, query, asking_user_dict)
        
        # 3. Save to DB (We still save BOTH to history)
        chat_message = ChatMessage(
            owner_email=current_user.email,
            user_query=query_to_save,
            ai_response=ai_response_text
        )
        await chat_messages_collection.insert_one(chat_message.model_dump())

        # 4. Return HTML Fragment (AI RESPONSE ONLY)
        # The user message is injected via JS optimistically
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
        print(f"Chat Error: {e}")
        return HTMLResponse(f'<div class="p-3 bg-red-50 text-red-600 rounded-lg text-sm text-center">Error: {str(e)}</div>')

@router.get("/chat/history", response_class=HTMLResponse)
async def get_chat_history(current_user: User = Depends(get_current_authenticated_user)):
    """
    Fetches chat history. Returns pairs of User + AI messages.
    """
    history_cursor = chat_messages_collection.find(
        {"owner_email": current_user.email}
    ).sort("timestamp", 1)
    
    history_list = await history_cursor.to_list(length=50)
    
    if not history_list:
        return HTMLResponse('''
            <div class="flex flex-col items-center justify-center h-full text-gray-400 space-y-4 opacity-60">
                <svg class="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-.5.5-.5.5H9z"></path></svg>
                <p class="text-sm font-medium">No messages yet. Start a consultation!</p>
            </div>
        ''')

    html_content = ""
    for msg in history_list:
        html_content += f"""
        <div class="flex flex-col space-y-4 mb-6">
            <div class="self-end bg-indigo-600 text-white px-5 py-3 rounded-2xl rounded-tr-none max-w-[80%] shadow-md">
                <p class="text-sm">{msg.get('user_query')}</p>
            </div>
            <div class="self-start bg-white border border-gray-100 text-gray-800 px-5 py-3 rounded-2xl rounded-tl-none max-w-[85%] shadow-sm">
                <div class="flex items-center gap-2 mb-1">
                    <span class="text-xs font-bold text-indigo-600 uppercase tracking-wider">Aarogya AI</span>
                </div>
                <div class="prose prose-sm text-gray-700 leading-relaxed max-w-none">
                    {msg.get('ai_response', '').replace('\n', '<br>')}
                </div>
            </div>
        </div>
        """
    return HTMLResponse(html_content)