import os
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Firebase initialization
def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    if not firebase_admin._apps:
        service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
        
        if service_account_path and os.path.exists(service_account_path):
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
        else:
            # For production, use default credentials
            firebase_admin.initialize_app()
    
    # Get the Firestore database ID from environment variable
    database_id = os.getenv('FIRESTORE_DATABASE_ID', '(default)')
    
    # Return Firestore client with specific database
    return firestore.client(database_id=database_id)

# Google Cloud Configuration
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
GCP_BUCKET_NAME = os.getenv('GCP_BUCKET_NAME')
GCP_LOCATION = os.getenv('GCP_LOCATION', 'us-central1')
VERTEX_AI_MODEL = os.getenv('VERTEX_AI_MODEL', 'gemini-1.5-pro')
FIRESTORE_DATABASE_ID = os.getenv('FIRESTORE_DATABASE_ID', '(default)')
SIMPLIFY_DEFAULT_VERSION = os.getenv('SIMPLIFY_DEFAULT_VERSION', 'v1')
