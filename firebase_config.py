import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, auth
from typing import Optional, Dict, Any

def initialize_firebase():
    """Initialize Firebase with credentials from environment variable"""
    try:
        # Get Firebase credentials from environment variable
        firebase_credentials_json = os.getenv('FIREBASE_CREDENTIALS_JSON')
        
        if not firebase_credentials_json:
            raise ValueError(
                "FIREBASE_CREDENTIALS_JSON environment variable is not set. "
                "Please set this variable with the complete JSON content of your Firebase service account key."
            )
        
        # Parse the JSON string
        try:
            firebase_credentials_dict = json.loads(firebase_credentials_json)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON in FIREBASE_CREDENTIALS_JSON environment variable: {str(e)}"
            )
        
        # Validate required fields in the credentials
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        missing_fields = [field for field in required_fields if field not in firebase_credentials_dict]
        
        if missing_fields:
            raise ValueError(
                f"Missing required fields in Firebase credentials: {', '.join(missing_fields)}"
            )
        
        # Create credentials object
        firebase_creds = credentials.Certificate(firebase_credentials_dict)
        
        # Initialize Firebase app
        firebase_admin.initialize_app(firebase_creds)
        
        print(f"Firebase initialized successfully for project: {firebase_credentials_dict.get('project_id')}")
        
    except Exception as e:
        print(f"Error initializing Firebase: {str(e)}")
        raise

def get_firestore_client():
    """Get Firestore client instance"""
    try:
        return firestore.client()
    except Exception as e:
        print(f"Error getting Firestore client: {str(e)}")
        raise

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify Firebase JWT token and return user info"""
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except auth.ExpiredIdTokenError:
        print("Token has expired")
        return None
    except auth.RevokedIdTokenError:
        print("Token has been revoked")
        return None
    except auth.InvalidIdTokenError:
        print("Invalid token")
        return None
    except Exception as e:
        print(f"Error verifying token: {str(e)}")
        return None

# Initialize Firebase on module import
try:
    initialize_firebase()
    db = get_firestore_client()
except Exception as e:
    print(f"Failed to initialize Firebase: {str(e)}")
    # Set db to None so the app can handle the error gracefully
    db = None 