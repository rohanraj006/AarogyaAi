from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)

db = client.aarogyadb
user_collection = db.users

chat_messages_collection = db.chat_messages #this stores the chat history
reports_collection = db.reports #this stores the uploaded reports of the document
connection_requests_collection = db.connection_requests
appointments_collection = db.appointments