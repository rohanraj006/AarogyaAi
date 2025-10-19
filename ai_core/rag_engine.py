# ai_core/rag_engine.py

import json
import os
from pinecone import Pinecone
from dotenv import load_dotenv
import google.generativeai as genai
from sentence_transformers import SentenceTransformer

load_dotenv()

# --- Gemini Setup (for all AI tasks) ---
try:
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=gemini_api_key)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
    print("Gemini client configured successfully.")
except Exception as e:
    print(f"Error configuring Gemini: {e}")
    gemini_model = None

try:
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    pc = Pinecone(api_key=pinecone_api_key)
    pinecone_index = pc.Index("aarogya-knowledge-base")
except Exception as e:
    print(f"error config pinecone: {e}")
    pinecone_index = None

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# --- FUNCTION 1: Using Gemini for Patient Chat (Now with Pinecone) ---
def get_rag_response(query: str, user_email: str):
    if not gemini_model or not pinecone_index:
        return "Error: AI clients are not configured."

    # 1. Create a vector of the user's query
    query_vector = embedding_model.encode(query).tolist()

    # 2. Query Pinecone to find relevant context for that specific user
    results = pinecone_index.query(
        vector=query_vector,
        top_k=3, # Get the top 3 most relevant text chunks
        filter={"owner_email": user_email}
    )
    
    context = "No personal context found for this user."
    if results and results['matches']:
        context = "\n\n".join([match['metadata']['text'] for match in results['matches']])

    prompt = f"""You are a friendly and empathetic medical AI assistant named Aarogya.

Your instructions are:
1.  Your primary goal is to answer the user's questions clearly, empathetically, and safely.
2.  Use your own knowledge, but you MUST prioritize the information from the user's personal documents in the "CONTEXT" section to tailor your response.
3.  If a user asks for a prescription or diagnosis (e.g., "What should I take for my headache?"), you MUST follow this procedure: offer a safe, non-medical suggestion and offer to contact a doctor. Your response should be very similar to this example: "I understand you're not feeling well, getting some rest can often help. Would you like me to notify a doctor about your symptoms?"
4. suggest some home remedies.

CONTEXT FROM USER'S DOCUMENTS:
---
{context}
---

USER'S QUESTION: {query}
"""
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return "Sorry, I am having trouble connecting to the AI service right now."


# --- FUNCTION 2: Using Gemini for Doctor-Facing Summarization ---
def get_summary_response(document_text: str):
    """
    Uses the Gemini API to generate a high-quality summary.
    """
    if not gemini_model:
        return "Error: Gemini client is not configured."

    prompt = f"""You are an expert medical summarization assistant. Your task is to read the following medical report and generate a concise summary.

Focus on extracting the key findings, diagnoses, abnormal values, and recommended treatment plans. Present the summary in clear, easy-to-read bullet points.

MEDICAL REPORT TEXT:
---
{document_text}
---

SUMMARY:"""

    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        return "Sorry, there was an error communicating with the Gemini AI model."
    
def process_dictation(dictated_text: str):
    """
    Uses the Gemini API to convert unstructured doctor dictation into structured JSON data.
    """
    if not gemini_model:
        return None

    # This prompt forces the AI to output a structured JSON that aligns with the Pydantic schemas.
    prompt = f"""You are a clinical documentation specialist AI. Your task is to extract all medical findings, diagnoses, and medication prescriptions from the following unstructured doctor's dictated notes.

You MUST respond ONLY with a single JSON object that strictly adheres to the following format. Do not include any text outside the JSON block.

JSON SCHEMA:
{{
  "diagnosis": [
    {{
      "condition": "string (e.g., Acute Bronchitis)",
      "diagnosed_on": "string (ISO 8601 format, e.g., 2025-10-19T10:00:00Z). Use today's date if not specified.",
      "notes": "string (Key findings related to this diagnosis)"
    }}
  ],
  "medications": [
    {{
      "name": "string (e.g., Amoxicillin)",
      "dosage": "string (e.g., 500mg)",
      "frequency": "string (e.g., twice daily for 7 days)"
    }}
  ]
}}

DICTATED NOTES:
---
{dictated_text}
---

JSON OUTPUT:"""

    try:
        response = gemini_model.generate_content(prompt)
        
        # We assume the AI returns valid JSON string
        json_string = response.text.strip()
        
        # Attempt to parse the JSON output
        return json.loads(json_string)
        
    except json.JSONDecodeError as e:
        print(f"AI returned invalid JSON: {response.text} Error: {e}")
        return {"error": "AI failed to produce structured notes."}
    except Exception as e:
        print(f"Error during Gemini API call for dictation: {e}")
        return {"error": "Sorry, the AI service is unavailable."}