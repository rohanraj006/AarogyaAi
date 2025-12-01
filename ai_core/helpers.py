# ai_core/helpers.py

from database import user_collection, medical_records_collection, report_contents_collection
from bson import ObjectId

async def fetch_patient_context(user_email: str) -> dict:
    """
    Fetches the user document and their full medical record.
    Used by Chatbot, Wellness, and Report services.
    """
    # 1. Fetch User Document
    user_doc = await user_collection.find_one({"email": user_email})
    if not user_doc:
        return {"user_doc": None, "medical_record": {}}

    medical_record_doc = {}
    
    # 2. Only fetch medical record if user is a PATIENT
    if user_doc.get("user_type") == "patient":
        # Using email as patient_id as per schema
        medical_record_doc = await medical_records_collection.find_one({"patient_id": user_email}) or {}
        
        # 3. Expand report references (Embed content for AI context)
        if medical_record_doc.get("reports"):
            updated_reports = []
            for report_ref in medical_record_doc.get("reports", []):
                if isinstance(report_ref, dict) and report_ref.get("content_id"):
                    try:
                        if not ObjectId.is_valid(report_ref["content_id"]): continue
                        content_oid = ObjectId(report_ref["content_id"])
                        
                        # Fetch actual text content
                        report_content_doc = await report_contents_collection.find_one({"_id": content_oid})
                        
                        if report_content_doc and report_content_doc.get("content_text"):
                            # Create copy and inject content
                            report_with_content = report_ref.copy()
                            report_with_content["description"] = report_content_doc["content_text"]
                            updated_reports.append(report_with_content)
                        else:
                            updated_reports.append(report_ref)
                    except Exception as e:
                        print(f"Error expanding report {report_ref.get('content_id')}: {e}")
                        updated_reports.append(report_ref)
            
            medical_record_doc["reports"] = updated_reports
            
    return {
        "user_doc": user_doc,
        "medical_record": medical_record_doc
    }