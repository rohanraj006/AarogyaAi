# ai_core/chatbot_service.py

import os
import google.generativeai as genai
from dotenv import load_dotenv
import logging
import json
from datetime import datetime
import asyncio
from typing import Dict, Any, Optional

load_dotenv()
logger = logging.getLogger(__name__)

# Configure the Generative AI model
API_KEY = os.getenv("GEMINI_API_KEY")
if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
        SINGLE_MODEL_NAME = os.getenv("SINGLE_MODEL_NAME", "gemini-2.5-flash")
    except Exception as e:
        logger.error(f"Error configuring Google Generative AI: {e}")
        SINGLE_MODEL_NAME = None
else:
     SINGLE_MODEL_NAME = None


class MedicalChatbot:
    """A class to manage interactions with a single LLM model for chat, summary, and report generation."""
    def __init__(self, model_name: str = SINGLE_MODEL_NAME):
        self.model_name = model_name
        self.model = None

        if not self.model_name:
            logger.warning("AI model not initialized: GEMINI_API_KEY is missing.")
            return

        try:
            self.model = genai.GenerativeModel(model_name=self.model_name)
            logger.info(f"Chatbot initialized with model: {self.model_name}")
        except Exception as e:
            logger.error(f"Error initializing generative model {self.model_name}: {e}")
            self.model = None
            
    # --- Helper Methods for Context Formatting ---
    # These assume a combined dict structure is passed from the caller
    def _format_patient_data(self, user_doc: dict) -> str:
        """Formats basic patient data from the User document."""
        # Simple extraction from the updated User schema
        formatted_data = f"Patient ID: {user_doc.get('aarogya_id', user_doc.get('_id'))}\n"
        formatted_data += f"Name: {user_doc.get('name', {}).get('first', 'N/A')} {user_doc.get('name', {}).get('last', '')}\n"
        formatted_data += f"Age: {user_doc.get('age', 'N/A')}\n"
        return formatted_data

    def _format_doctor_data(self, doctor_data: dict) -> str:
        """Formats the doctor's data for context."""
        if not doctor_data: return "No doctor data available."
        formatted_data = f"Doctor Name: Dr. {doctor_data.get('name', {}).get('first', 'N/A')} {doctor_data.get('name', {}).get('last', '')}\n"
        formatted_data += f"Specialty: {doctor_data.get('specialization', 'Medical Practitioner')}\n"
        formatted_data += f"Contact: {doctor_data.get('email', 'N/A')}"
        return formatted_data
    # --- End Helper Methods ---

    async def generate_response(self, patient_data: dict, doctor_query: str, chat_context: str) -> str:
        """Generates a response using patient data (medical record) and RAG context (Pinecone)."""
        if not self.model: return "AI model is not initialized."

        user_doc = patient_data.get('user_doc', {})
        user_type = user_doc.get('user_type', 'patient') # Detect user type
        
        # --- LOGIC BRANCH: DOCTOR VS PATIENT ---
        
        if user_type == 'doctor':
            # Context for DOCTORS
            doctor_name = f"{user_doc.get('name', {}).get('first', '')} {user_doc.get('name', {}).get('last', '')}"
            patient_list = user_doc.get('patient_list', [])
            
            system_instruction = (
                f"You are a smart medical assistant named Aarogya AI, assisting Dr. {doctor_name}. "
                "Your goal is to help the doctor manage their practice and patients efficiently. "
                "You have access to the doctor's profile and their list of connected patients below. "
                "If the doctor asks for their patient list, you SHOULD provide it based on the data below."
                "do not confuse with doctor with a patient"
            )
            
            data_context = f"""
            --- DOCTOR PROFILE ---
            Name: Dr. {doctor_name}
            ID: {user_doc.get('aarogya_id')}
            Specialization: {user_doc.get('specialization', 'General')}
            
            --- CONNECTED PATIENTS LIST ---
            {', '.join(patient_list) if patient_list else 'No patients connected yet.'}
            """
            
        else:
            # Context for PATIENTS (Existing Logic)
            medical_record = patient_data.get('medical_record', {})
            patient_info_str = self._format_patient_data(user_doc)
            medical_record_str = json.dumps(medical_record, indent=2)
            
            system_instruction = (
                "You are a helpful and empathetic medical AI assistant chatbot named Aarogya. "
                "You are talking directly to the patient. "
                "Your primary goal is to answer the user's questions clearly, empathetically, and safely. "
                "If a user asks for a prescription or diagnosis, you MUST offer a safe, non-medical suggestion and advise them to consult a doctor."
            )
            
            data_context = f"""
            --- PATIENT STRUCTURED DATA ---
            {patient_info_str}
            {medical_record_str}
            """

        # Combine into full prompt
        full_prompt = f"""{system_instruction}

{data_context}

--- CONTEXT FROM KNOWLEDGE BASE (RAG) ---
{chat_context}
---

USER'S QUESTION: {doctor_query}
"""

        try:
            response = await asyncio.to_thread(self.model.generate_content, full_prompt)
            return response.text if hasattr(response, 'text') and response.text is not None else "Sorry, the AI model returned an empty response."
        except Exception as e:
            logger.error(f"Error generating RAG/Chat response: {e}")
            return f"Sorry, I could not generate a response at this time. Error: {type(e).__name__}"

    async def summarize_medical_record(self, patient_data: dict) -> str:
        """Generates a summary of the patient's full medical record."""
        if not self.model: return "AI model is not initialized for summarization."
        
        patient_context = self._format_patient_data(patient_data.get('user_doc', {}))
        medical_record_json = json.dumps(patient_data.get('medical_record', {}), indent=2)

        system_instruction = (
            "You are a medical assistant chatbot. Your task is to provide a concise summary "
            "of the provided patient medical data. Highlight key information such as "
            "diagnoses, current medications, known allergies, and significant history. "
            "Present the summary clearly and structured."
        )

        full_prompt = f"{system_instruction}\n\nPatient Basic Data:\n{patient_context}\n\nPatient Medical Record (JSON):\n{medical_record_json}\n\nAssistant Summary:"

        try:
            response = await asyncio.to_thread(self.model.generate_content, full_prompt)
            return response.text if hasattr(response, 'text') and response.text is not None else "Sorry, the AI model returned an empty summary response."
        except Exception as e:
            logger.error(f"Error generating medical record summary: {e}")
            return f"Sorry, I could not generate the summary at this time. Error: {type(e).__name__}"

    async def generate_medical_report(self, patient_data: dict, doctor_data: dict, transcribed_text: str) -> str:
        """Formats transcribed text into a structured medical report using the AI model."""
        if not self.model: return "AI model is not initialized for report generation."
        if not transcribed_text or not transcribed_text.strip(): return "No transcribed text provided."

        patient_context = self._format_patient_data(patient_data.get('user_doc', {}))
        doctor_context = self._format_doctor_data(doctor_data)

        prompt_parts = [
            "You are an AI medical assistant. Format the following dictated notes into a structured medical report.",
            "Do not Include a header or footer that will be done with the help of report lab .",
            "Possible sections could include Subjective, Objective, Assessment, and Plan. Organize the dictated notes into these sections if they fit naturally, or present as a clear narrative.",
            "Ensure the output is ONLY the formatted medical report text. Do NOT include any introductory or concluding conversational sentences.",
            "The output which you give should not have asterisks becuase the formatting can't be done in the report seperate using --> ",
            "\n--- Doctor Information ---",
            doctor_context,
            "\n\n--- Patient Information ---",
            patient_context,
            "\n\n--- Dictated Notes ---",
            transcribed_text,
            "\n\n--- Formatted Medical Report ---",
            "Generate the formatted medical report below:"
        ]
        full_prompt = "\n".join(prompt_parts)

        try:
            response = await asyncio.to_thread(self.model.generate_content, full_prompt)
            return response.text.strip() if hasattr(response, 'text') and response.text is not None else "AI model generated no text response."
        except Exception as e:
            logger.error(f"Error calling AI model for report generation: {e}")
            return f"Error communicating with AI model for report generation: {type(e).__name__}: {e}"

    async def generate_structured_response(self, prompt: str, patient_data: Dict[str, Any], doctor_data: Dict[str, Any]) -> str:
        """Sends a structured prompt (like a JSON extraction prompt) to the AI model."""
        if not self.model: return "AI model is not initialized for structured response."
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text if hasattr(response, 'text') and response.text is not None else "AI model generated no text response for structured task."
        except Exception as e:
            logger.error(f"Error during AI structured response generation: {e}", exc_info=True)
            return f"Error communicating with AI model for structured task: {type(e).__name__}: {e}"
        
    async def summarize_report_text(self, report_text: str) -> str:
        """Generates a summary of a single piece of text."""
        if not self.model: return "AI model is not initialized for summarization."
        if not report_text or not report_text.strip():
            return "No text was provided to summarize."

        system_instruction = (
            "You are a medical assistant chatbot. Your task is to provide a concise summary "
            "of the following medical report text. Extract key findings, diagnoses, and treatments mentioned. "
            "Present the summary as clean text, without any markdown like '**' or headers."
        )

        full_prompt = f"{system_instruction}\n\n--- REPORT TEXT TO SUMMARIZE ---\n{report_text}\n\n--- SUMMARY ---"

        try:
            response = await asyncio.to_thread(self.model.generate_content, full_prompt)
            return response.text if hasattr(response, 'text') and response.text is not None else "Sorry, the AI model returned an empty summary response."
        except Exception as e:
            logger.error(f"Error generating single report summary: {e}")
            return f"Sorry, I could not generate the summary at this time. Error: {type(e).__name__}"