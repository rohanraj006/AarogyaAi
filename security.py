# security.py

import bcrypt
import os
import secrets
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status, Request, Response
from bson import ObjectId
from typing import Optional

# UPDATED IMPORTS: Use async database client and new session/user schemas
from models.schemas import User, UserSession, SESSION_COOKIE_NAME, SESSION_EXPIRATION_MINUTES
from database import user_collection, db 

load_dotenv()

# --- Password Utilities (Keep as is) ---
def verify_password(plain_password: str, hashed_password:str) -> bool:
    """Compares a plain text password with a stored hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    """Returns a secure bcrypt hash."""
    hashed_bytes = bcrypt.hashpw(password.encode('utf-8'),bcrypt.gensalt())
    return hashed_bytes.decode('utf-8')


# --- Session Management Functions ---
def get_sessions_collection():
    """Returns the Motor sessions collection."""
    return db.get_collection("sessions")

async def create_user_session(user_id: str, user_type: str) -> str:
    """Creates a session document, saves it to DB, and returns the secure random token."""
    sessions_collection = get_sessions_collection()
    session_token = secrets.token_hex(32)
    
    session = UserSession(token=session_token, user_id=user_id, user_type=user_type)
    session_dict = session.model_dump(mode='json', exclude={'id'})

    try:
        insert_result = await sessions_collection.insert_one(session_dict)
        if not insert_result.inserted_id:
             raise Exception("Failed to insert session document")
        return session_token
    except Exception as e:
        print(f"Error creating session document for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create session document")


async def get_current_session(request: Request) -> Optional[UserSession]:
    """Retrieves and validates the session from the cookie and database."""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        return None

    sessions_collection = get_sessions_collection()
    try:
        session_doc = await sessions_collection.find_one({"token": session_token})

        if session_doc:
            if '_id' in session_doc and isinstance(session_doc['_id'], ObjectId):
                 session_doc['_id'] = str(session_doc['_id'])

            session = UserSession(**session_doc)
            now_utc = datetime.now(timezone.utc)

            if session.expires_at < now_utc:
                await sessions_collection.delete_one({"_id": ObjectId(session.id)})
                return None

            # Update activity timestamp (sliding window)
            await sessions_collection.update_one(
                {"_id": ObjectId(session.id)},
                {"$set": {"last_active": datetime.now(timezone.utc)}}
            )
            return session
        else:
             return None

    except Exception as e:
        print(f"Error during session retrieval: {e}")
        return None


async def delete_user_session(request: Request, response: Response):
    """Deletes the session from the DB and removes the cookie."""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        sessions_collection = get_sessions_collection()
        try:
            await sessions_collection.delete_one({"token": session_token})
        except Exception as e:
            print(f"Error deleting session from DB: {e}")

        response.delete_cookie(SESSION_COOKIE_NAME, path="/")


# --- Authentication Dependency ---
async def get_current_authenticated_user(request: Request):
    """Fetches the authenticated User object based on the session cookie."""
    session: Optional[UserSession] = await get_current_session(request)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials: No valid session.",
            headers={"WWW-Authenticate": "Bearer"}, 
        )

    user_id_str = session.user_id 
    
    try:
        # Fetch the full user document from the 'users' collection (now using Motor)
        user_doc = await db.users.find_one({"_id": ObjectId(user_id_str)})
    except Exception as e:
        print(f"Error fetching user {user_id_str} from users collection: {e}")
        user_doc = None

    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials: User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Return the Pydantic User model instance
    return User(**user_doc)