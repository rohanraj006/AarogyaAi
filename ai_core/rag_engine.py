# ai_core/rag_engine.py (Refactored)

import json
import os
from pinecone import Pinecone
from dotenv import load_dotenv
import google.generativeai as genai
from sentence_transformers import SentenceTransformer
import asyncio
from database import user_collection, medical_records_collection # Use Motor collections
from bson import ObjectId # Import ObjectId

# Import the new service layer
from .chatbot_service import MedicalChatbot
from .parser_service import MedicalReportParser, convert_unserializable_types
from models.schemas import MedicalRecord, Diagnosis, Medication 

load_dotenv()

# --- Initialize AI Services ---
try:
    chatbot_service = MedicalChatbot()
    gemini_model = chatbot_service.model 
except Exception as e:
    print(f"Error configuring MedicalChatbot: {e}")
    chatbot_service = None
    gemini_model = None

parser_service = None
if chatbot_service and chatbot_service.model:
    try:
        parser_service = MedicalReportParser(chatbot_service=chatbot_service)
        print("MedicalReportParser configured successfully.")
    except Exception as e:
        print(f"Error configuring MedicalReportParser: {e}")
        parser_service = None

# --- Pinecone Setup (Keep as is for RAG) ---
try:
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    pc = Pinecone(api_key=pinecone_api_key)
    pinecone_index = pc.Index("aarogya-knowledge-base")
except Exception as e:
    print(f"error config pinecone: {e}")
    pinecone_index = None

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


# --- NEW HELPER: Fetch Context for Chatbot ---
async def fetch_patient_context(user_email: str) -> dict:
    """Fetches user document and medical record document, including report content for AI context."""
    user_doc = await user_collection.find_one({"email": user_email})
    patient_id_str = str(user_doc["_id"]) if user_doc and user_doc.get("_id") else None

    medical_record_doc = {}
    if patient_id_str:
        # NOTE: Using email as patient_id in Codebase 1 context
        medical_record_doc = await medical_records_collection.find_one({"patient_id": user_email})
    
    if medical_record_doc and medical_record_doc.get("reports"):
        medical_record_doc = medical_record_doc.copy()
        updated_reports = []
        for report_ref in medical_record_doc.get("reports", []):
            if report_ref.get("content_id"):
                try:
                    content_oid = ObjectId(report_ref["content_id"])
                    content_doc = await report_contents_collection.find_one({"_id": content_oid})
                    if content_doc and content_doc.get("content") is not None:
                         report_ref["description"] = content_doc["content"]
                    else:
                         report_ref["description"] = "Content not available."
                except Exception:
                     report_ref["description"] = "Content loading error."
            updated_reports.append(report_ref)
        medical_record_doc["reports"] = updated_reports


    return {
        "user_doc": user_doc,
        "medical_record": medical_record_doc or {}
    }


# --- FUNCTION 1: Using Gemini for Patient Chat (Refactored) ---
async def get_rag_response(query: str, user_email: str):
    if not chatbot_service or not pinecone_index or not chatbot_service.model:
        return "Error: AI services are not configured."

    # 1. Fetch Patient Context
    patient_context_data = await fetch_patient_context(user_email)
    if not patient_context_data['user_doc']:
        return "Error: User not found in database."

    # 2. Query Pinecone to find relevant context
    query_vector = embedding_model.encode(query).tolist()
    results = pinecone_index.query(
        vector=query_vector,
        top_k=3, 
        filter={"owner_email": user_email}
    )
    
    rag_context = "No personal context found for this user."
    if results and results['matches']:
        rag_context = "\n\n".join([match['metadata']['text'] for match in results['matches']])

    # 3. Use the new service layer to generate the response
    try:
        response_text = await chatbot_service.generate_response(
            patient_data=patient_context_data,
            doctor_query=query, 
            chat_context=rag_context
        )
        return response_text
    except Exception as e:
        print(f"Error during Chatbot service call: {e}")
        return "Sorry, I am having trouble connecting to the AI service right now."


# --- FUNCTION 2: Using Gemini for Doctor-Facing Summarization (Refactored) ---

async def get_summary_response(user_email: str):
    """Uses the new service layer to generate a high-quality summary of the patient's full medical record."""
    if not chatbot_service or not chatbot_service.model:
        return "Error: AI client is not configured."

    patient_context_data = await fetch_patient_context(user_email)
    if not patient_context_data['user_doc']:
        return "Error: User not found in database."

    try:
        # Note: If patient_context_data has no medical_record, the service will summarize 'empty' data.
        summary = await chatbot_service.summarize_medical_record(patient_context_data)
        return summary
    except Exception as e:
        print(f"Error during MedicalChatbot API call for summary: {e}")
        return "Sorry, there was an error communicating with the Gemini AI model."


# --- FUNCTION 3: Converting Dictation to Structured JSON (Refactored) ---
async def process_dictation(dictated_text: str, patient_email: str):
    """
    Uses the new MedicalReportParser service to convert dictated text into 
    structured data (Diagnosis and Medication lists), mimicking the old interface.
    """
    if not parser_service or not parser_service.chatbot_service.model:
        return {"error": "AI client is not configured for dictation processing."}

    # 1. Fetch Patient Context (assuming patient_email is the patient being dictated about)
    patient_context_data = await fetch_patient_context(patient_email)
    
    # 2. Get the DOCTOR who is calling this (assuming doctor email is passed in the route, but
    # here we use a placeholder as the signature is hardcoded to only patient_email)
    # The actual implementation of the calling route will need to be updated to pass the doctor's email/doc
    doctor_placeholder = {"email": "system_doctor@aarogya.ai", "name": {"first": "System", "last": "Doctor"}, "user_type": "doctor"}

    try:
        # 3. Call the parser service to extract structured data
        extracted_data = await parser_service.parse_medical_report(
            report_text=dictated_text,
            patient_data=patient_context_data,
            doctor_data=doctor_placeholder
        )
        
        # 4. Adapt output to match Codebase 1's expected return for validation:
        # Codebase 1 expects keys 'diagnosis' (List[Diagnosis]) and 'medications' (List[Medication])
        return {
            # Mapping from the parser's keys to Codebase 1's legacy keys (which now point to rich schemas)
            "diagnosis": extracted_data.get("diagnoses", []), 
            "medications": extracted_data.get("medications", []),
            # NOTE: Other extracted fields (allergies, etc.) are ignored here,
            # so the consuming route in doctor_routes.py must be updated to process the full record.
        }
        
    except ValueError as e:
        return {"error": f"AI failed to produce structured notes (Invalid JSON/Format): {e}"}
    except Exception as e:
        print(f"Error during parser service call: {e}")
        return {"error": "Sorry, the AI service is unavailable."}
    
async def predict_symptom_severity(patient_email: str, reason: str, patient_notes: str) -> str:
    """Uses the MedicalChatbot service to predict symptom severity based on medical history and notes."""
    # NOTE: The chatbot_service must be imported and initialized in this file.
    from ai_core.rag_engine import chatbot_service 
    
    if not chatbot_service or not chatbot_service.model:
        return "Unknown (AI Service Unavailable)"

    patient_data_context = await fetch_patient_context(patient_email)
    
    user_doc = patient_data_context.get('user_doc')
    medical_record = patient_data_context.get('medical_record')

    if not user_doc:
        return "Unknown (Patient Data Not Found)"
        
    # Prepare data for the AI call
    medical_info_str = f"""
    Patient Basic Info: {user_doc.get('email')}, Age: {user_doc.get('age', 'N/A')}, Gender: {user_doc.get('gender', 'N/A')}
    Medical Record (JSON): {json.dumps(medical_record)}
    Reason for Visit: {reason or 'Not provided'}
    Symptoms Description: {patient_notes or 'Not provided'}
    """

    prompt = f"""
    Based on the following patient medical information, predict the severity of the symptoms described. Return only one of the following severity levels as plain text: 'Very Serious', 'Moderate', 'Normal'. Do not include any explanations, markdown symbols, or additional text. Analyze the history, reason for visit, and symptoms description to make an informed prediction.

    {medical_info_str}
    """

    try:
        response = await asyncio.to_thread(chatbot_service.model.generate_content, prompt)
        severity = response.text.strip().replace('*', '')
        valid_severities = ["Very Serious", "Moderate", "Normal"]
        if severity not in valid_severities:
            return "Moderate" if "pain" in (reason + patient_notes).lower() else "Normal"
        return severity
    except Exception as e:
        print(f"Error predicting symptom severity with Gemini: {e}")
        return "Unknown (AI Call Failed)"