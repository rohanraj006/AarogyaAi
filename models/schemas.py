# models/schemas.py (OVERHAUL)

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Any
from datetime import datetime, timedelta, timezone # Added timedelta, timezone
from bson import ObjectId # Added ObjectId
import secrets
# NOTE: User/Patient specific fields are consolidated into the main User schema.

# --- 1. Session Management Schemas (From Step 1) ---
SESSION_COOKIE_NAME = "session_token"
SESSION_EXPIRATION_MINUTES = 1440 

class UserSession(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    token: str
    user_id: str
    user_type: str
    login_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=SESSION_EXPIRATION_MINUTES))

    class Config:
        allow_population_by_field_name = True
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True
# --- End Session Management ---


# --- 2. Detailed Core Models (NEW from Codebase 2) ---
class Name(BaseModel):
    first: str
    middle: Optional[str] = None
    last: str

class Address(BaseModel):
    street: str
    city: str
    state: str
    zip: str
    country: str

class EmergencyContact(BaseModel):
    name: str
    phone: str
    relationship: str

class Medication(BaseModel):
    name: str
    dosage: str
    frequency: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    notes: Optional[str] = None

class Diagnosis(BaseModel):
    disease: str
    year: Optional[int] = None
    diagnosis_date: Optional[datetime] = None
    notes: Optional[str] = None

class Prescription(BaseModel):
    doctor_id: str 
    medication: str
    dosage: str
    frequency: str
    date: datetime
    refillable: bool
    refill_count: int
    notes: Optional[str] = None

class Consultation(BaseModel):
    appointment_id: str
    doctor_id: str
    date: datetime
    notes: Optional[str] = None
    diagnosis: Optional[str] = None
    followup_date: Optional[datetime] = None

class Immunization(BaseModel):
    vaccine: str
    date: datetime
    lot_number: Optional[str] = None
    administered_by: str

class ReportContent(BaseModel):
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Report(BaseModel):
    # This replaces Codebase 1's old Report schema but is adapted to hold references
    id: Optional[str] = Field(alias="_id", default=None)
    filename: str
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    owner_email: str
    content_id: Optional[str] = None # String ObjectId of the actual content document
    report_type: Optional[str] = None
    description: Optional[str] = None 

    model_config = {
        'populate_by_name': True
    }

class MedicalRecord(BaseModel):
    # The primary structured medical data store
    patient_id: str
    current_medications: List[Medication] = []
    diagnoses: List[Diagnosis] = []
    prescriptions: List[Prescription] = []
    consultation_history: List[Consultation] = []
    reports: List[Report] = []
    allergies: List[str] = []
    immunizations: List[Immunization] = []
    family_medical_history: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
# --- End NEW Core Models ---


# --- 3. Updated User and Request Schemas ---

class User(BaseModel):
    
    id: Optional[str] = Field(alias="_id", default=None)
    email: str
    hashed_password: str
    aarogya_id: str
    user_type: str
    patient_list: List[str] = [] 
    doctor_list: List[str] = [] 
    is_public: bool = False
    is_authorized: bool = False
    
    # Patient Detail Fields (Optional since doctors/admins won't have them)
    name: Optional[Name] = None
    phone_number: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    address: Optional[Address] = None
    emergency_contact: Optional[EmergencyContact] = None
    registration_date: Optional[datetime] = None
    date_of_birth: Optional[str] = None 

    # Add this Config class
    class Config:
        allow_population_by_field_name = True
        json_encoders = {ObjectId: str}


class UserCreate(BaseModel):
    email: str
    password: str

class ChatRequest(BaseModel):
    # Updated to support advanced actions
    query: Optional[str] = Field(None)
    action: str = Field('ask', description="Action to perform: 'ask' or 'summarize'. Defaults to 'ask'.")
    
class ChatMessageBase(BaseModel):
    user_query: str
    ai_response: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatMessage(ChatMessageBase):
    owner_email: str

class ConnectionRequestModel(BaseModel):
    # Renamed from ConnectionRequest to avoid conflict with Report
    id: Optional[str] = Field(alias="_id", default=None)
    doctor_email: str
    patient_email: str
    status: Literal["pending","accepted", "rejected"] = "pending"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_config = {
        'populate_by_name': True
    }

class DoctorInfo(BaseModel):
    email: str
    aarogya_id: str
    is_public: bool
    is_authorized: bool

class AppointmentRequestModel(BaseModel):
    # Updated with severity prediction fields
    id: Optional[str] = Field(alias="_id", default=None)
    patient_email: str
    doctor_email: str 
    reason: str
    status: Literal["pending", "confirmed","rejected"]
    meeting_link: Optional[str] = None
    appointment_time: Optional[datetime]= None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    # NEW FIELDS
    patient_notes: Optional[str] = None
    predicted_severity: Optional[str] = None

    class Config:
        allow_population_by_field_name = True
        json_encoders = {ObjectId: str} 

class AppointmentConfirmBody(BaseModel):
    request_id: str
    appointment_time: datetime

class DictationSaveBody(BaseModel):
    # Needs a patient ID/email and the extracted data to save
    patient_email: str
    medical_record: MedicalRecord # NOTE: This now uses the rich MedicalRecord structure

class ReportContentRequest(BaseModel):
    content_text: str = Field(..., description="Raw or formatted text content.")

class ReportPDFRequest(BaseModel):
    report_content_text: str = Field(..., description="Formatted report text to be converted to PDF.")