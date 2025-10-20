# main.py

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles 
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List

# Import our tools and schemas
from ai_core.rag_engine import get_rag_response, get_summary_response # UPDATED: Import async services
from routes import user_routes, report_routes, doctor_routes, connection_routes, admin_routes,appointment_routes, ui_routes

from security import get_current_authenticated_user # UPDATED: Use new session dependency
from database import chat_messages_collection # Motor collection
from models.schemas import User, ChatRequest, ChatMessage, ChatMessageBase

app = FastAPI(
    title="AarogyaAI",
    description=" medical ai assistant",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Include all the different routers for our application (KEEP AS IS)
app.include_router(ui_routes.router, prefix="", tags=["UI & Pages"])
app.include_router(user_routes.router, prefix="/users", tags=["Users"])
app.include_router(report_routes.router, prefix="/reports", tags=["Reports"])
app.include_router(doctor_routes.router, prefix="/doctor", tags=["Doctor"])
app.include_router(connection_routes.router, prefix="/connections", tags=["Connections"])
app.include_router(admin_routes.router, prefix="/admin",tags=["Admin"])
app.include_router(appointment_routes.router, prefix="/appointments", tags=["Appointments"])

@app.get("/")
def read_root():
    """This is the main endpoint of the API."""
    return {"message": "Welcome to your Arogya AI Backend! The service is running."}

@app.post("/chat")
async def chat_with_rag(
    request: ChatRequest,
    current_user: User = Depends(get_current_authenticated_user) # UPDATED: Use new dependency
):
    """
    Receives a user query, gets a personalized response from the AI
    based on the user's documents and structured data, and saves the conversation.
    """
    if request.action == 'summarize':
        if current_user.user_type != 'patient':
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only patients can request a summary of their record.")
        # If action is summarize, call the summary service (new feature)
        ai_response_text = await get_summary_response(user_email=current_user.email)
        query_to_save = "Request for Medical Record Summary"

    elif request.action == 'ask' and request.query:
        # 1. Get the AI's response, now using async service wrapper
        ai_response_text = await get_rag_response(request.query, user_email=current_user.email)
        query_to_save = request.query
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action or missing query.")

    # 2. Create a chat message object
    chat_message = ChatMessage(
        owner_email=current_user.email,
        user_query=query_to_save,
        ai_response=ai_response_text
    )

    # 3. Save the message to the database
    await chat_messages_collection.insert_one(chat_message.model_dump()) # Use await for Motor & model_dump
    
    return {"response": ai_response_text}


@app.get("/chat/history", response_model=List[ChatMessageBase])
async def get_chat_history(current_user: User = Depends(get_current_authenticated_user)): # UPDATED: Use new dependency

    """
    Retrieves the chat history for the currently logged-in user.
    """
    history_cursor = chat_messages_collection.find(
        {"owner_email": current_user.email}
    ).sort("timestamp", -1)
    
    history_list = await history_cursor.to_list(length=100) # Use await for Motor

    return [ChatMessageBase(**msg) for msg in history_list]