# ai_core/parser_service.py

import logging
from typing import Dict, Any, List
from .chatbot_service import MedicalChatbot # Assuming in the same directory
import json
from datetime import datetime
from bson import ObjectId

logger = logging.getLogger(__name__)

# Helper function to convert non-JSON-serializable types to strings recursively
def convert_unserializable_types(data: Any) -> Any:
    """Recursively converts non-JSON-serializable types (like ObjectId, datetime) to strings."""
    if isinstance(data, dict):
        return {k: convert_unserializable_types(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_unserializable_types(item) for item in data]
    elif isinstance(data, ObjectId):
        return str(data)
    elif isinstance(data, datetime):
        return data.isoformat()
    else:
        return data


class MedicalReportParser:
    """Service for parsing medical report text using an AI model to extract structured medical information."""
    def __init__(self, chatbot_service: MedicalChatbot):
        if not isinstance(chatbot_service, MedicalChatbot):
             raise TypeError("MedicalReportParser requires a valid MedicalChatbot instance.")
        self.chatbot_service = chatbot_service
        logger.info("MedicalReportParser initialized.")

    async def parse_medical_report(self, report_text: str, patient_data: Dict[str, Any], doctor_data: Dict[str, Any]) -> Dict[str, Any]:
        """Uses the AI model to parse the given report text and extract structured medical entities."""
        if not report_text or not report_text.strip(): return {}
        if not self.chatbot_service.model: raise RuntimeError("AI model not available for structured parsing.")

        patient_data_cleaned = convert_unserializable_types(patient_data)
        doctor_data_cleaned = convert_unserializable_types(doctor_data)

        patient_context = json.dumps(patient_data_cleaned.get("user_doc", {}), indent=2)
        medical_record_context = json.dumps(patient_data_cleaned.get("medical_record", {}), indent=2)
        doctor_context = json.dumps(doctor_data_cleaned, indent=2)

        prompt = f"""
You are an expert medical assistant. Your task is to carefully read the following medical report and extract structured information.
Focus on extracting the following entities mentioned in the Medical Report Text:
- **Medications:** List of medications mentioned. For each medication, include name, dosage, frequency, start_date (YYYY-MM-DD), end_date (YYYY-MM-DD, or null if ongoing/duration not specified), and notes (optional).
- **Diagnoses:** List of medical diagnoses mentioned. For each diagnosis, include disease name, diagnosis_date (YYYY-MM-DD, or null if date not specified), and notes (optional).
- **Allergies:** List of patient allergies mentioned (as strings).
- **Consultations:** List of consultations mentioned. For each consultation, include date (YYYY-MM-DD), notes (optional), diagnosis (optional string), and followup_date (YYYY-MM-DD, or null if none specified).
- **Immunizations:** List of immunizations mentioned. For each, include vaccine name, date (YYYY-MM-DD), and notes (optional).

Present the extracted information as a JSON object with the following top-level keys: "medications", "diagnoses", "allergies", "consultations", "immunizations". If a category is not mentioned, its value should be an empty list `[]`. Do NOT include any text outside the JSON object.

Patient and Doctor Context:
---
Patient Information:
{patient_context}

Medical Record:
{medical_record_context}
---

Medical Report Text to Parse:
---
{report_text}
---

JSON Output:
"""

        try:
            raw_ai_output = await self.chatbot_service.generate_structured_response(
                prompt=prompt,
                patient_data=patient_data_cleaned,
                doctor_data=doctor_data_cleaned
            )

            # Clean and parse the JSON output
            cleaned_output = raw_ai_output.strip()
            if cleaned_output.startswith("```json"): cleaned_output = cleaned_output[len("```json"):]
            if cleaned_output.endswith("```"): cleaned_output = cleaned_output[:-len("```")]
            parsed_data = json.loads(cleaned_output.strip())

            # Ensure expected top-level keys exist and are lists
            extracted_data = {
                "diagnoses": parsed_data.get("diagnoses", []),
                "medications": parsed_data.get("medications", []),
                "allergies": parsed_data.get("allergies", []),
                "consultations": parsed_data.get("consultations", []),
                "immunizations": parsed_data.get("immunizations", []),
            }
            return extracted_data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from AI output: {e}")
            raise ValueError(f"AI returned invalid JSON format: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            raise RuntimeError(f"Error processing AI output: {e}") from e