import os
from googleapiclient.discovery import build
from google.oauth2 import service_account

SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive',
]

def get_services():
    """Build and return authenticated Docs and Drive service clients."""
    creds = service_account.Credentials.from_service_account_file(
        'service_account.json',
        scopes=SCOPES,
    )
    docs_service = build('docs', 'v1', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return docs_service, drive_service


def create_and_share_doc(title: str, sections: dict, recipient_email: str) -> str:
    """
    Create a Google Doc, write all grant sections into it,
    share it with recipient_email, and return the doc URL.
    """

    pass