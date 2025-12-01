# test_meet.py
import sys
import os
from datetime import datetime, timedelta

# Ensure we can import from the app folder
sys.path.append(os.getcwd())

try:
    from app.services.google_service import create_google_meet_link
except ImportError:
    print("Error: Could not import google_service. Make sure you are running this from the project root.")
    sys.exit(1)

def test_generation():
    print("--- Starting Google Meet Link Test ---")
    
    # 1. Define meeting details
    summary = "Test Consultation (Script)"
    # Schedule for 1 hour from now
    start_time = datetime.now() + timedelta(hours=1)
    attendees = [] # Add test emails here if you want: ['test@example.com']

    print(f"Attempting to create event: '{summary}' at {start_time}")

    # 2. Call the function
    # Note: If token.json is missing/invalid, this will open a browser window for login!
    try:
        link = create_google_meet_link(summary, start_time, attendees)
        
        print("\n------------------------------------------------")
        print(f"Returned Link: {link}")
        print("------------------------------------------------\n")

        if link and link.startswith("https://meet.google.com/"):
            print("✅ SUCCESS: Valid Google Meet link generated.")
        else:
            print("❌ FAILURE: Generated link does not look correct.")
            
    except Exception as e:
        print(f"❌ ERROR: An exception occurred: {e}")

if __name__ == "__main__":
    # Check for credentials
    if not os.path.exists('credentials.json'):
        print("⚠️ WARNING: credentials.json not found in root folder!")
        print("You must download the OAuth Client ID JSON from Google Cloud Console.")
    else:
        test_generation()