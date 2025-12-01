# app/services/google_service.py

import os
import datetime
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    """Authenticates and returns the Google Calendar service."""
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Error refreshing token: {e}")
                os.remove('token.json')
                return None
        else:
            if not os.path.exists('credentials.json'):
                logger.error("credentials.json not found. Cannot generate Google Meet link.")
                return None
                
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                # Opens a local browser for auth
                creds = flow.run_local_server(port=0)
            except Exception as e:
                logger.error(f"Error during OAuth flow: {e}")
                return None
                
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Error building service: {e}")
        return None

def create_google_meet_link(summary: str, start_time: datetime.datetime, attendee_emails: list = []) -> str:
    """
    Creates a Google Calendar event with a Meet conference and returns the link.
    """
    service = get_calendar_service()
    if not service:
        return "https://meet.google.com/ (Manual Setup Required - Check Server Logs)"

    # Set duration to 30 minutes by default
    end_time = start_time + datetime.timedelta(minutes=30)

    # Format event body
    event = {
        'summary': summary,
        'description': 'Consultation via Aarogya AI Platform',
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'UTC',
        },
        'attendees': [{'email': email} for email in attendee_emails],
        'conferenceData': {
            'createRequest': {
                'requestId': f"aarogya-{int(datetime.datetime.now().timestamp())}",
                'conferenceSolutionKey': {'type': 'hangoutsMeet'}
            }
        },
    }

    try:
        event = service.events().insert(
            calendarId='primary', 
            body=event, 
            conferenceDataVersion=1
        ).execute()
        
        meet_link = event.get('conferenceData', {}).get('entryPoints', [{}])[0].get('uri')
        return meet_link or "Link creation failed"
        
    except Exception as e:
        logger.error(f"Google Calendar API Error: {e}")
        return "Error creating link"