# main.py

from fastapi import FastAPI, Depends
from pydantic import BaseModel
from typing import List

# Import our tools and schemas
from ai_core.rag_engine import get_rag_response
from routes import user_routes, report_routes, doctor_routes, connection_routes, admin_routes,appointment_routes

from security import get_current_user
from models.schemas import User, ChatRequest, ChatMessage, ChatMessageBase
from database import chat_messages_collection

app = FastAPI(
    title="AarogyaAI",
    description=" medical ai assistant",
    version="0.1.0",
)

# Include all the different routers for our application
app.include_router(user_routes.router, prefix="/users", tags=["Users"])
app.include_router(report_routes.router, prefix="/reports", tags=["Reports"])
app.include_router(doctor_routes.router, prefix="/doctor", tags=["Doctor"])
app.include_router(connection_routes.router, prefix="/connections", tags=["Connections"])
app.include_router(admin_routes.router, prefic="/admin",tags=["Admin"])
app.include_router(appointment_routes.router, prefix="/appointments", tags=["Appointments"])

@app.get("/")
def read_root():
    """This is the main endpoint of the API."""
    return {"message": "Welcome to your Arogya AI Backend!"}

@app.post("/chat")
async def chat_with_rag(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Receives a user query, gets a personalized response from the AI
    based on the user's documents, and saves the conversation.
    """
    # 1. Get the AI's response, now passing the user's email for personalization
    ai_response_text = get_rag_response(request.query, user_email=current_user.email)

    # 2. Create a chat message object
    chat_message = ChatMessage(
        owner_email=current_user.email,
        user_query=request.query,
        ai_response=ai_response_text
    )

    # 3. Save the message to the database
    chat_messages_collection.insert_one(chat_message.dict())
    
    return {"response": ai_response_text}


@app.get("/chat/history", response_model=List[ChatMessageBase])
async def get_chat_history(current_user: User = Depends(get_current_user)):

    """
    Retrieves the chat history for the currently logged-in user.
    """
    history = chat_messages_collection.find(
        {"owner_email": current_user.email}
    ).sort("timestamp", -1)
    
    return [ChatMessageBase(**msg) for msg in history]