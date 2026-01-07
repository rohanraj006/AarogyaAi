# ai_core/chatbot_service.py

import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Literal, Optional

import google.generativeai as genai
from dotenv import load_dotenv


load_dotenv()
logger = logging.getLogger(__name__)

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("SINGLE_MODEL_NAME", "gemini-2.5-flash")

if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    logger.warning("GEMINI_API_KEY not found. AI disabled.")

class MedicalChatbot:
    """
    Aarogya AI Core Chatbot Service

    This service NEVER guesses roles.
    Caller must explicitly provide:
      - actor: doctor | patient
      - mode: general | patient_context
    """

    def __init__(self):
        self.model = None
        if API_KEY:
            try:
                self.model = genai.GenerativeModel(MODEL_NAME)
                logger.info(f"Aarogya AI initialized with model: {MODEL_NAME}")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini model: {e}")

    async def generate_response(
        self,
        *,
        actor: Literal["doctor", "patient"],
        mode: Literal["general", "patient_context"],
        query: str,
        patient_context: Optional[Dict[str, Any]],
        actor_profile: Dict[str, Any]
    ) -> str:
        """
        Main router. This is the ONLY method routes should call.
        """

        if not self.model:
            return "AI service is currently unavailable."

        if actor == "doctor" and mode == "general":
            return await self._doctor_general(query, actor_profile)

        if actor == "doctor" and mode == "patient_context":
            return await self._doctor_patient(query, patient_context, actor_profile)

        if actor == "patient" and mode == "general":
            return await self._patient_general(query)

        if actor == "patient" and mode == "patient_context":
            return await self._patient_own_record(query, patient_context)

        return "Invalid request configuration."

    async def _doctor_general(self, query: str, doctor: dict) -> str:
        prompt = f"""
You are Aarogya AI, assisting a licensed medical professional.

Doctor:
Name: Dr. {doctor.get('name', {}).get('first', '')} {doctor.get('name', {}).get('last', '')}
Specialization: {doctor.get('specialization', 'General Physician')}

Rules:
- Answer professionally and concisely
- No patient assumptions
- Medical accuracy is mandatory
- If unsure, say so

Doctor Question:
{query}
"""
        return await self._run(prompt)

    async def _doctor_patient(
        self,
        query: str,
        patient_data: dict,
        doctor: dict
    ) -> str:
        prompt = f"""
You are Aarogya Clinical AI assisting a doctor.

Doctor:
Dr. {doctor.get('name', {}).get('first', '')} {doctor.get('name', {}).get('last', '')}

Rules:
- Clinical tone
- Bullet points preferred
- Highlight red flags
- Do NOT invent data
- Base answers strictly on provided record

Patient Record:
{json.dumps(patient_data, indent=2, default=str)}

Doctor Question:
{query}
"""
        return await self._run(prompt)

    async def _patient_general(self, query: str) -> str:
        prompt = f"""
You are Aarogya, a medical information assistant.

Rules:
- Educational only
- No diagnosis
- No prescriptions
- Use simple language

User Question:
{query}
"""
        return await self._run(prompt)

    async def _patient_own_record(
        self,
        query: str,
        patient_data: dict
    ) -> str:
        prompt = f"""
You are Aarogya, a compassionate medical assistant.

Rules:
- Explain in simple terms
- No diagnosis or treatment changes
- Encourage consulting a doctor for new symptoms
- Do NOT invent data

Patient Medical Record:
{json.dumps(patient_data, indent=2, default=str)}

Patient Question:
{query}
"""
        return await self._run(prompt)
   
    async def _run(self, prompt: str) -> str:
        try:
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt
            )
            return response.text.strip() if response and response.text else "No response generated."
        except Exception as e:
            logger.error(f"AI generation error: {e}")
            return "An error occurred while generating the response."

    async def summarize_medical_record(self, patient_data: dict) -> str:
        prompt = f"""
Summarize this medical record for a doctor.
Highlight:
- Diagnoses
- Medications
- Allergies
- Recent events

Record:
{json.dumps(patient_data, indent=2, default=str)}
"""
        return await self._run(prompt)

    async def generate_medical_report(
        self,
        patient_data: dict,
        doctor_data: dict,
        transcribed_text: str
    ) -> str:
        prompt = f"""
You are a medical scribe.

Format the notes into:
Subjective
Objective
Assessment
Plan

Doctor:
Dr. {doctor_data.get('name', {}).get('first', '')} {doctor_data.get('name', {}).get('last', '')}

Patient:
{json.dumps(patient_data, indent=2, default=str)}

Dictation:
{transcribed_text}
"""
        return await self._run(prompt)

    async def generate_wellness_plan(self, patient_data: dict) -> str:
        prompt = f"""
Create a personalized wellness plan.

Sections (exact):
Diet Recommendations:
Healthy Habits:
Things to Avoid:
Exercise Plan:

Patient Data:
{json.dumps(patient_data, indent=2, default=str)}
"""
        return await self._run(prompt)

    async def predict_severity(
        self,
        patient_data: dict,
        reason: str,
        notes: str
    ) -> str:
        prompt = f"""
Classify urgency as EXACTLY one:
Very Serious
Moderate
Normal

Patient:
{json.dumps(patient_data, indent=2, default=str)}

Reason:
{reason}

Symptoms:
{notes}
"""
        result = await self._run(prompt)
        result = result.replace("*", "").strip()
        return result if result in {"Very Serious", "Moderate", "Normal"} else "Moderate"

    async def predict_specialty_from_symptoms(self, symptoms: str) -> str:
        prompt = f"""
Map symptoms to ONE medical specialization.

Symptoms:
{symptoms}

Return ONLY specialization name.
"""
        return await self._run(prompt)
    
    async def generate_clinical_snapshot(self, patient_context: dict) -> str:
    
        prompt = f"""
                You are Aarogya Clinical AI.

                Create a PRE-CONSULTATION SUMMARY for a doctor.
                Rules:
                - Bullet points
                - Clinical tone
                - No explanations
                - Highlight risks
                - Max 10 lines

                Patient Medical Record:
                {json.dumps(patient_context, indent=2, default=str)}

                Output:
            """
        return await self._run(prompt)

    async def generate_structured_response(self, prompt: str, **kwargs) -> str:
        """
        Executes a prompt intended to return structured (JSON) data.
        """
        if not self.model:
            return "{}"
        
        # You can reuse the existing _run executor
        return await self._run(prompt)



