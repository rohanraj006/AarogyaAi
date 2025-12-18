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
    def _format_patient_data(self, user_doc: dict) -> str:
        """Formats basic patient data from the User document."""
        if not user_doc:
            return "Patient data not found."
            
        formatted_data = f"Patient ID: {user_doc.get('aarogya_id', user_doc.get('_id'))}\n"
        formatted_data += f"Name: {user_doc.get('name', {}).get('first', 'N/A')} {user_doc.get('name', {}).get('last', '')}\n"
        formatted_data += f"Age: {user_doc.get('age', 'N/A')}\n"
        formatted_data += f"Gender: {user_doc.get('gender', 'N/A')}\n"
        formatted_data += f"Blood Group: {user_doc.get('blood_group', 'N/A')}\n"
        return formatted_data

    def _format_doctor_data(self, doctor_data: dict) -> str:
        """Formats the doctor's data for context."""
        if not doctor_data: return "No doctor data available."
        formatted_data = f"Doctor Name: Dr. {doctor_data.get('name', {}).get('first', 'N/A')} {doctor_data.get('name', {}).get('last', '')}\n"
        formatted_data += f"Specialty: {doctor_data.get('specialization', 'Medical Practitioner')}\n"
        formatted_data += f"Contact: {doctor_data.get('email', 'N/A')}"
        return formatted_data

    # --- MODIFIED: generate_response accepts asking_user ---
    async def generate_response(self, patient_data: dict, query: str, asking_user: dict) -> str:
        """
        Generates a response using direct context injection.
        Now context-aware: Knows if user is Doctor or Patient.
        """
        if not self.model: return "AI model is not initialized."

        user_doc = patient_data.get('user_doc', {})
        medical_record = patient_data.get('medical_record', {})
        
        # Build Data Strings
        patient_info_str = self._format_patient_data(user_doc)
        medical_record_str = json.dumps(medical_record, indent=2, default=str)
        
        # --- DYNAMIC SYSTEM INSTRUCTION ---
        user_type = asking_user.get("user_type", "patient")
        asker_name = f"{asking_user.get('name', {}).get('first', '')} {asking_user.get('name', {}).get('last', '')}"

        if user_type == "doctor":
            system_instruction = (
                f"You are Aarogya, a medical AI assistant helping Dr. {asker_name}. "
                "You are analyzing the medical records of the patient described below. "
                "Your tone should be professional, clinical, and concise. "
                "Highlight medical insights, potential red flags, and answer the doctor's specific queries strictly based on the data. "
                "Do NOT invent medical history."
            )
        else:
            system_instruction = (
                f"You are Aarogya, a helpful and empathetic medical AI assistant helping {asker_name}. "
                "You are answering questions based strictly on their own medical data provided below. "
                "Explain medical terms simply. Do not invent medical history. "
                "If the answer is not in the data, say so. Always advise consulting a doctor for new symptoms."
            )
        
        full_prompt = f"""{system_instruction}

--- PATIENT DATA ---
{patient_info_str}

--- MEDICAL RECORD ---
{medical_record_str}

USER QUESTION: {query}
"""

        try:
            response = await asyncio.to_thread(self.model.generate_content, full_prompt)
            return response.text if hasattr(response, 'text') and response.text is not None else "Sorry, the AI model returned an empty response."
        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            return f"Sorry, I encountered an error: {str(e)}"

    async def summarize_medical_record(self, patient_data: dict) -> str:
        """Generates a summary of the patient's full medical record."""
        if not self.model: return "AI model is not initialized."
        
        user_doc = patient_data.get('user_doc', {})
        medical_record = patient_data.get('medical_record', {})
        
        patient_context = self._format_patient_data(user_doc)
        medical_record_json = json.dumps(medical_record, indent=2, default=str)

        prompt = f"""
        You are a medical assistant. Summarize the following patient medical record for a doctor.
        Highlight current medications, recent diagnoses, allergies, and critical history.
        
        Patient: {patient_context}
        Record: {medical_record_json}
        
        Summary:
        """

        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text if hasattr(response, 'text') else "No summary generated."
        except Exception as e:
            logger.error(f"Error summarizing: {e}")
            return "Error generating summary."

    async def generate_medical_report(self, patient_data: dict, doctor_data: dict, transcribed_text: str) -> str:
        """Formats transcribed text into a structured medical report."""
        if not self.model: return "AI model is not initialized."
        
        patient_context = self._format_patient_data(patient_data.get('user_doc', {}))
        doctor_context = self._format_doctor_data(doctor_data)
        current_date_str = datetime.now().strftime("%B %d, %Y")

        prompt = f"""
        You are a medical scribe. Format the following dictated notes into a professional medical report.
        Use standard sections: Subjective, Objective, Assessment, Plan.
        Do NOT use markdown (like ** or ##). Use simple text formatting with clear headers.
        
        Date: {current_date_str}
        Doctor: {doctor_context}
        Patient: {patient_context}
        
        Dictated Notes:
        {transcribed_text}
        
        Formatted Report:
        """

        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text.strip() if hasattr(response, 'text') else "No report generated."
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return f"Error generating report: {e}"

    async def generate_structured_response(self, prompt: str, patient_data: Dict[str, Any], doctor_data: Dict[str, Any]) -> str:
        """Sends a prompt expecting a JSON response."""
        if not self.model: return "{}"
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            # Basic cleanup if the model adds markdown
            text = response.text
            if text:
                text = text.strip()
                if text.startswith("```json"): text = text[7:]
                if text.endswith("```"): text = text[:-3]
                return text
            return "{}"
        except Exception as e:
            logger.error(f"Error during structured response: {e}")
            return "{}"
        
    async def summarize_report_text(self, report_text: str) -> str:
        """Summarizes a specific text block."""
        if not self.model: return "AI unavailable."
        try:
            response = await asyncio.to_thread(self.model.generate_content, f"Summarize this medical text concisely:\n\n{report_text}")
            return response.text
        except Exception as e:
            return f"Error: {e}"

    # --- NEW FEATURE: Wellness Plan ---
    async def generate_wellness_plan(self, patient_data: dict) -> str:
        if not self.model: return "AI unavailable."
        
        user_doc = patient_data.get('user_doc', {})
        record = patient_data.get('medical_record', {})
        
        info_str = f"Age: {user_doc.get('age')}, Gender: {user_doc.get('gender')}\n"
        info_str += f"Diagnoses: {json.dumps(record.get('diagnoses', []), default=str)}\n"
        info_str += f"Medications: {json.dumps(record.get('current_medications', []), default=str)}"
        
        prompt = f"""
        Generate a personalized wellness plan for this patient.
        Include exactly these 4 sections with clear headers ending in a colon:
        Diet Recommendations:
        Healthy Habits:
        Things to Avoid:
        Exercise Plan:
        
        Patient Info:
        {info_str}
        """
        
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error generating wellness plan: {e}")
            return "Could not generate wellness plan."

    # --- NEW FEATURE: Symptom Severity (Triage) ---
    async def predict_severity(self, patient_data: dict, reason: str, notes: str) -> str:
        if not self.model: return "Normal"
        
        user_doc = patient_data.get('user_doc', {})
        record = patient_data.get('medical_record', {})
        
        prompt = f"""
        Analyze this patient's request to predict appointment urgency.
        Patient: {user_doc.get('age')}yo {user_doc.get('gender')}.
        History: {json.dumps(record.get('diagnoses', []), default=str)}
        Reason for Visit: {reason}
        Symptoms: {notes}
        
        Task: Classify severity as exactly one of these: 'Very Serious', 'Moderate', 'Normal'.
        Return ONLY the classification word.
        """
        
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            text = response.text.strip().replace("*", "").replace("'", "").replace('"', "")
            if text in ['Very Serious', 'Moderate', 'Normal']:
                return text
            return "Moderate" # Default fallback
        except Exception as e:
            logger.error(f"Error predicting severity: {e}")
            return "Normal"