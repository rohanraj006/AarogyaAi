# database.py

from motor.motor_asyncio import AsyncIOMotorClient 
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI") 
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in .env file.")


client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)

db = client.aarogyadb 
user_collection = db.users
sessions_collection = db.sessions 
chat_messages_collection = db.chat_messages
reports_collection = db.reports
connection_requests_collection = db.connection_requests
appointments_collection = db.appointments
medical_records_collection = db.medical_records
report_contents_collection = db.report_contents 
instant_meetings_collection = db.instant_meetings
