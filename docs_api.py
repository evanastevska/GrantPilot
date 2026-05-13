import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive',
]

FOLDER_ID = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')


def get_services():
    creds = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    #refresh if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        #save refreshed token
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    if not creds or not creds.valid:
        raise Exception(
            "OAuth token missing or invalid. "
            "Run python authorize.py to re-authenticate."
        )

    docs_service = build('docs', 'v1', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return docs_service, drive_service


def create_and_share_doc(title: str, sections: dict, issues: list, recipient_email: str) -> str:
    docs_service, drive_service = get_services()

    #create doc on personal Google account
    doc = docs_service.documents().create(body={'title': title}).execute()
    doc_id = doc['documentId']

    #move into the Cinema Verde shared folder
    drive_service.files().update(
        fileId=doc_id,
        addParents=FOLDER_ID,
        removeParents='root',
        fields='id, parents'
    ).execute()

    #build content
    requests = []
    current_index = 1

    if issues:
        issue_text = "FLAGGED ISSUES\n"
        for issue in issues:
            issue_text += f"• {issue}\n"
        issue_text += "\n"

        requests.append({
            'insertText': {
                'location': {'index': current_index},
                'text': issue_text
            }
        })
        requests.append({
            'updateParagraphStyle': {
                'range': {
                    'startIndex': current_index,
                    'endIndex': current_index + len("FLAGGED ISSUES")
                },
                'paragraphStyle': {'namedStyleType': 'HEADING_1'},
                'fields': 'namedStyleType'
            }
        })
        current_index += len(issue_text)

    for section_name in [
        "Executive Summary",
        "Organization Background",
        "Statement of Need",
        "Project Description",
        "Goals and Objectives",
        "Evaluation Plan",
        "Budget Narrative",
        "Conclusion",
        "Notes for Reviewer",
    ]:
        content = sections.get(section_name, "[Section not written]")
        section_text = f"{section_name}\n{content}\n\n"

        requests.append({
            'insertText': {
                'location': {'index': current_index},
                'text': section_text
            }
        })
        requests.append({
            'updateParagraphStyle': {
                'range': {
                    'startIndex': current_index,
                    'endIndex': current_index + len(section_name)
                },
                'paragraphStyle': {'namedStyleType': 'HEADING_1'},
                'fields': 'namedStyleType'
            }
        })
        current_index += len(section_text)

    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={'requests': requests}
    ).execute()

    #share with whoever submitted the form
    drive_service.permissions().create(
        fileId=doc_id,
        body={
            'type': 'user',
            'role': 'writer',
            'emailAddress': recipient_email,
        },
        sendNotificationEmail=True,
    ).execute()

    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    return doc_url