import os
from typing import Optional
import firebase_admin
from firebase_admin import credentials, firestore, auth
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    firebase_credentials_path: str = "firebase-credentials.json"

    class Config:
        env_file = ".env"

settings = Settings()

def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    if not firebase_admin._apps:
        cred = credentials.Certificate(settings.firebase_credentials_path)
        firebase_admin.initialize_app(cred)
    return firestore.client()

def get_firestore_client():
    """Get Firestore client instance"""
    return firestore.client()

def verify_token(token: str) -> Optional[dict]:
    """Verify Firebase ID token"""
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        print(f"Error verifying token: {e}")
        return None

# Initialize Firebase on module import
db = initialize_firebase() 