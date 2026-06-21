import os
from dotenv import load_dotenv
from utils.constants import Constants

# Load environment variables
load_dotenv()

# Google Cloud Configuration
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
GCP_BUCKET_NAME = os.getenv('GCP_BUCKET_NAME')
GCP_LOCATION = os.getenv('GCP_LOCATION', 'us-central1')
VERTEX_AI_MODEL = os.getenv('VERTEX_AI_MODEL', 'gemini-1.5-pro')
FIRESTORE_DATABASE_ID = os.getenv('FIRESTORE_DATABASE_ID', '(default)')
CARE_PLAN_DEFAULT_VERSION = os.getenv(
    Constants.CARE_PLAN_DEFAULT_VERSION_ENV_VAR,
    Constants.CARE_PLAN_DEFAULT_VERSION_FALLBACK,
)
