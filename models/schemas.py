from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from typing import Literal
from bson import ObjectId

class Medication(BaseModel):
    name: str
    dosage: str
    frequency: str

class Diagnosis(BaseModel):
    condition: str
    diagnosed_on: datetime
    notes: Optional[str]=None

class MedicalRecord(BaseModel):
    diagnosis: List[Diagnosis] = []
    medications: List[Medication] = []

class Patient(BaseModel):
    name: str
    age: int = Field(gt=0,description="age must be a positive integer")
    gender: str
    medical_record: MedicalRecord = Field(default_factory=MedicalRecord)

class ChatRequest(BaseModel):
    query: str

class ChatMessageBase(BaseModel):
    user_query: str
    ai_response: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatMessage(ChatMessageBase):
    owner_email: str

class User(BaseModel):
    email: str
    hashed_password: str
    aarogya_id: str
    user_type: str
    patient_list: List[str] = [] # For doctors
    doctor_list: List[str] = []  # For patients
    is_public: bool = False
    is_authorized: bool = False

class UserCreate(BaseModel):
    email: str
    password: str

class Report(BaseModel):
    id:str = Field(alias="_id",default=None)
    filename: str
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    owner_email: str 

    class Config:
        allow_population_by_field_name = True

class ConnectionRequest(BaseModel):
    id:str = Field(alias="_id",default=None)
    doctor_email: str
    patient_email: str
    status: Literal["pending","accepted", "rejected"] = "pending"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    class Config:
        allow_population_by_field_name = True
    

class DoctorInfo(BaseModel):
    email: str
    aarogya_id: str
    is_public: bool
    is_authorized: bool

class AppointmentRequestModel(BaseModel):
    id: str = Field(alias="_id", default=None)
    patient_email: str
    doctor_email: str 
    reason: str
    status: Literal["pending", "confirmed","rejected"]
    meeting_link: Optional[datetime] = None
    appointment_time: Optional[datetime]= None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        allow_population_by_field_name = True
        # NEW: Ensure Pydantic can convert ObjectId to str for responses
        json_encoders = {ObjectId: str} 

class AppointmentConfirmBody(BaseModel):
    """Schema for a doctor confirming an appointment request."""
    request_id: str
    appointment_time: datetime

class DictationSaveBody(BaseModel):
    """Schema for the doctor to send validated dictation data to be saved."""
    patient_email: str
    medical_record: MedicalRecord