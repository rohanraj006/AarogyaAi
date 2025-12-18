# models/schemas.py

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Any
from datetime import datetime, timedelta, timezone 
from bson import ObjectId
import secrets

# --- 1. Session Management Schemas ---
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

    # V2 Configuration
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }

# --- 2. Detailed Core Models ---

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
    dosage: Optional[str] = None
    # FIX: Made frequency optional to handle null values from DB
    frequency: Optional[str] = None 
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    notes: Optional[str] = None

class Diagnosis(BaseModel):
    # FIX: Added alias to map 'disease_name' from DB to 'disease'
    disease: str = Field(alias="disease_name") 
    year: Optional[int] = None
    diagnosis_date: Optional[datetime] = None
    notes: Optional[str] = None

    model_config = {
        "populate_by_name": True
    }

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

# FIX: Created EmbeddedReport for reports inside MedicalRecord
class EmbeddedReport(BaseModel):
    """Schema for reports embedded inside the MedicalRecord document."""
    report_id: Optional[str] = None
    report_type: Optional[str] = None
    date: Optional[datetime] = None
    content_id: Optional[str] = None
    description: Optional[str] = None 

# This is the full Report model for the 'reports' collection (File uploads)
class Report(BaseModel):
    id: Optional[str] = Field(alias="_id", default=None)
    filename: str
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    owner_email: str
    content_id: Optional[str] = None 
    report_type: Optional[str] = None
    description: Optional[str] = None 

    model_config = {
        "populate_by_name": True
    }

class MedicalRecord(BaseModel):
    # The primary structured medical data store
    patient_id: str
    current_medications: List[Medication] = []
    diagnoses: List[Diagnosis] = []
    prescriptions: List[Prescription] = []
    consultation_history: List[Consultation] = []
    
    # FIX: Use EmbeddedReport here instead of the full Report schema
    reports: List[EmbeddedReport] = [] 
    
    allergies: List[str] = []
    immunizations: List[Immunization] = []
    family_medical_history: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True
    }

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
    
    # Patient Detail Fields
    name: Optional[Name] = None
    phone_number: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    address: Optional[Address] = None
    emergency_contact: Optional[EmergencyContact] = None
    registration_date: Optional[datetime] = None
    date_of_birth: Optional[str] = None 
    specialization: Optional[str] = None
    blood_group:Optional[str] = None
    
    # These fields are strings in the User document (summary)
    medical_conditions: Optional[str] = None 
    allergies: Optional[str] = None           
    current_medications: Optional[str] = None 
    
    model_config = {
        "populate_by_name": True
    }

class UserCreate(BaseModel):
    email: str
    password: str

class ChatRequest(BaseModel):
    query: Optional[str] = Field(None)
    action: str = Field('ask', description="Action: 'ask' or 'summarize'")
    
class ChatMessageBase(BaseModel):
    user_query: str
    ai_response: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    patient_id: Optional[str] = None

class ChatMessage(ChatMessageBase):
    owner_email: str

class ConnectionRequestModel(BaseModel):
    id: Optional[str] = Field(alias="_id", default=None)
    doctor_email: str
    patient_email: str
    status: Literal["pending","accepted", "rejected"] = "pending"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = {
        "populate_by_name": True
    }

class DoctorInfo(BaseModel):
    email: str
    aarogya_id: str
    is_public: bool
    is_authorized: bool

class AppointmentRequestModel(BaseModel):
    id: Optional[str] = Field(alias="_id", default=None)
    patient_email: str
    doctor_email: str 
    reason: str
    status: str 
    meeting_link: Optional[str] = None
    appointment_time: Optional[datetime]= None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_link_active: bool = False
    patient_notes: Optional[str] = None
    predicted_severity: Optional[str] = None

    model_config = {
        "populate_by_name": True
    } 

class AppointmentConfirmBody(BaseModel):
    request_id: str
    appointment_time: datetime

class DictationSaveBody(BaseModel):
    patient_email: str
    medical_record: MedicalRecord 

class ReportContentRequest(BaseModel):
    content_text: str = Field(..., description="Raw or formatted text content.")

class ReportPDFRequest(BaseModel):
    report_content_text: str = Field(..., description="Formatted report text to be converted to PDF.")