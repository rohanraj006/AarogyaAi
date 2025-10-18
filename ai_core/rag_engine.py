# ai_core/rag_engine.py

import os
import chromadb
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

# --- RAG Setup ---
client = chromadb.PersistentClient(path="db")
collection = client.get_collection(name="medical_knowledge")
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


# --- FUNCTION 1: Using Gemini for Patient Chat ---
def get_rag_response(query: str, user_email: str):
    """
    Handles patient chat using the Gemini API.
    Uses personalized RAG context to inform its answers.
    """
    if not gemini_model:
        return "Error: Gemini client is not configured."

    results = collection.query(
        query_embeddings=[embedding_model.encode(query).tolist()],
        n_results=5,
        where={"owner_email": user_email} 
    )
    
    context = "No personal context found for this user."
    if results and results['documents'] and results['documents'][0]:
        context = "\n\n".join(results['documents'][0])

    prompt = f"""You are a friendly and empathetic medical AI assistant named Aarogya.
Your goal is to answer the user's questions clearly and safely.
Use your own knowledge, but you MUST prioritize the information from the user's personal documents in the "CONTEXT" section to tailor your response.
Never provide direct medical advice. Always encourage the user to consult a doctor.

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
        print(f"Error during Gemini API call: {e}")
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