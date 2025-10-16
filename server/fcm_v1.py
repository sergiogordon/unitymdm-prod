import os
import json
from google.oauth2 import service_account
import google.auth.transport.requests

SCOPES = ['https://www.googleapis.com/auth/firebase.messaging']

def _get_service_account_info():
    """
    Get Firebase service account credentials from either:
    1. FIREBASE_SERVICE_ACCOUNT_JSON secret (preferred - safe for public forks)
    2. FIREBASE_SERVICE_ACCOUNT_PATH file (backwards compatibility)
    
    Returns: dict with service account data
    """
    # Option 1: Direct JSON content from Replit Secret (recommended)
    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
    if service_account_json:
        try:
            return json.loads(service_account_json)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}\n"
                "Please paste the entire contents of your Firebase service account JSON file."
            )
    
    # Option 2: File path (backwards compatibility, less secure for public repos)
    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")
    if service_account_path:
        if not os.path.exists(service_account_path):
            raise FileNotFoundError(
                f"Service account file not found: {service_account_path}\n"
                "Consider using FIREBASE_SERVICE_ACCOUNT_JSON secret instead for better security."
            )
        with open(service_account_path, 'r') as f:
            return json.load(f)
    
    # Neither option provided
    raise ValueError(
        "Firebase credentials not configured. Set one of:\n"
        "  1. FIREBASE_SERVICE_ACCOUNT_JSON (recommended - paste JSON content into Replit Secret)\n"
        "  2. FIREBASE_SERVICE_ACCOUNT_PATH (file path - less secure for public forks)\n"
        "See DEPLOYMENT.md for detailed instructions."
    )

def get_access_token():
    service_account_info = _get_service_account_info()
    
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=SCOPES
    )
    
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    
    return credentials.token

def get_firebase_project_id():
    service_account_info = _get_service_account_info()
    
    project_id = service_account_info.get("project_id")
    
    if not project_id or project_id.strip() == "":
        raise ValueError(
            "Firebase service account data is missing 'project_id' field. "
            "Please ensure you copied the complete service account JSON from Firebase Console."
        )
    
    return project_id

def build_fcm_v1_url(project_id: str) -> str:
    return f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
