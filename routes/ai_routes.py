# routes/ai_routes.py

from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from typing import Optional
from bson import ObjectId
from markdown_it import MarkdownIt

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
md = MarkdownIt()

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
    instant_request_id: Optional[str] = Form(None),
    patient_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_authenticated_user)
):
    try:
        ai_response_text = "Sorry, I couldn't process that."
        query_to_save = query
        context_patient_id = None

        # ----------------------------------------------------
        # INSTANT CONSULT CHAT (DOCTOR)
        # ----------------------------------------------------
        if instant_request_id and current_user.user_type == "doctor":
            meeting = await instant_meetings_collection.find_one({
                "_id": ObjectId(instant_request_id),
                "doctor_id": str(current_user.id),
                "status": "accepted"
            })

            if not meeting:
                raise HTTPException(status_code=404, detail="Instant meeting not found")

            # Fetch patient context
            patient = await user_collection.find_one(
                {"_id": ObjectId(meeting["patient_id"])}
            )
            patient_context = await fetch_patient_context(patient["email"])

            ai_response_text = await chatbot.respond(
                actor="doctor",
                mode="patient_context",
                query=query,
                patient_context=patient_context,
                actor_profile=current_user.model_dump()
            )

        # ---------------------------------------------------------
        # DOCTOR FLOW
        # ---------------------------------------------------------
        if current_user.user_type == "doctor":

            # 🩺 Doctor WITH patient selected
            if patient_id:
                patient = await user_collection.find_one({"_id": ObjectId(patient_id)})
                if not patient or patient["email"] not in current_user.patient_list:
                    raise HTTPException(status_code=403, detail="Unauthorized patient access")

                patient_context = await fetch_patient_context(patient["email"])
                context_patient_id = patient_id
                query_to_save = f"[Patient: {patient.get('name', {}).get('first', 'Unknown')}] {query}"

                ai_response_text = await chatbot.generate_response(
                    actor="doctor",
                    mode="patient_context",
                    query=query,
                    patient_context=patient_context,
                    actor_profile=current_user.model_dump()
                )

            # 🧠 Doctor WITHOUT patient (general help)
            else:
                ai_response_text = await chatbot.generate_response(
                    actor="doctor",
                    mode="general",
                    query=query,
                    patient_context=None,
                    actor_profile=current_user.model_dump()
                )

        # ---------------------------------------------------------
        # PATIENT FLOW
        # ---------------------------------------------------------
        else:
            patient_context = await fetch_patient_context(current_user.email)

            ai_response_text = await chatbot.generate_response(
                actor="patient",
                mode="patient_context",
                query=query,
                patient_context=patient_context,
                actor_profile=current_user.model_dump()
            )

        # ---------------------------------------------------------
        # SAVE CHAT HISTORY
        # ---------------------------------------------------------
        chat_message = ChatMessage(
            owner_email=current_user.email,
            user_query=query_to_save,
            ai_response=ai_response_text,
            patient_id=context_patient_id
        )
        await chat_messages_collection.insert_one(chat_message.model_dump())

        # ---------------------------------------------------------
        # RENDER RESPONSE
        # ---------------------------------------------------------
        html_response = md.render(ai_response_text)

        return HTMLResponse(f"""
        <div class="flex flex-col space-y-4 mb-6 animate-fade-in">
            <div class="self-start bg-white border border-gray-100 text-gray-800 px-5 py-3 rounded-2xl rounded-tl-none max-w-[85%] shadow-sm">
                <span class="text-xs font-bold text-indigo-600 uppercase">Aarogya AI</span>
                <div class="prose prose-sm text-gray-700 max-w-none">
                    {html_response}
                </div>
            </div>
        </div>
        """)

    except Exception as e:
        return HTMLResponse(
            f'<div class="p-3 bg-red-50 text-red-600 rounded-lg text-sm">Error: {str(e)}</div>'
        )


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