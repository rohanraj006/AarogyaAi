# AarogyaAi/models.py

from pydantic import BaseModel, Field, EmailStr, BeforeValidator
from typing import Optional, Annotated
from bson import ObjectId
import datetime


PyObjectId = Annotated[
    str,
    BeforeValidator(str),
]

class User(BaseModel):
    """
    Represents a user document as it is stored in the MongoDB database.
    This model is the single source of truth for a user's data structure.
    """
    
    # The 'id' field in our Python code maps to the '_id' field in MongoDB.
    # It's optional because a new user object won't have an ID until it's saved.
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    
    # Standard user fields with type validation.
    username: str
    email: EmailStr  # Pydantic validates this is a correct email format.
    user_type: str   # Expected values: "patient" or "doctor".
    
    # This field stores the encrypted password, not the raw one.
    hashed_password: str
    
    # Automatically sets the creation timestamp when a new user is created.
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Config:
        """
        Pydantic model configuration settings.
        """
        # Allows Pydantic to create a model instance using the database field name '_id'.
        populate_by_name = True
        
        # Provides a rule for converting non-standard types (like ObjectId) to JSON.
        json_encoders = {ObjectId: str}
        
        # If the data from MongoDB has extra fields not defined in this model,
        # Pydantic will ignore them instead of raising an error.
        extra = "ignore"

