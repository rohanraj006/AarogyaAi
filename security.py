import bcrypt
import os
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pymongo import MongoClient
from models.schemas import User
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client.aarogyadb
user_collection = db.users

SEC_KEY = os.getenv("SECRET_KEY")
if not SEC_KEY:
    raise ValueError("no secret key in .env file")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 
if not SEC_KEY:
    raise ValueError("No SECRET_KEY set in the environment variables. Please check your .env file.")

def verify_password(plain_password: str, hashed_password:str) -> bool:
    """
    Compares a plain text password with a stored hash to see if they match.
    Returns True if they match, False otherwise.
    """
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    """
    Takes a plain text password and returns a secure bcrypt hash.
    """
    hashed_bytes = bcrypt.hashpw(password.encode('utf-8'),bcrypt.gensalt())
    return hashed_bytes.decode('utf-8')

def create_access_token(data: dict):
    """creates a new JWT(JSON web tokens) access tokens"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc)+timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp":expire})

    encode_jwt = jwt.encode(to_encode, SEC_KEY, algorithm=ALGORITHM) #type: ignore
    return encode_jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    """decodes the JWT to find and return the current user."""
    credentials_exception = HTTPException(
        status_code = status.HTTP_401_UNAUTHORIZED,
        detail="could not validate credentials",
        headers = {"WWW-Authentication":"Bearer"},
    )
    try:
        payload = jwt.decode(token, SEC_KEY,algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = user_collection.find_one({"email":email})
    if user is None:
        raise credentials_exception
    
    return User(**user)