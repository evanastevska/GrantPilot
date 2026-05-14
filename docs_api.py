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
    print("GET_SERVICES: starting", flush=True)
    creds = None
    token_path = os.environ.get('TOKEN_PATH', 'token.json')
    print(f"GET_SERVICES: token_path={token_path}", flush=True)
    print(f"GET_SERVICES: file exists={os.path.exists(token_path)}", flush=True)

    if os.path.exists(token_path):
        print("GET_SERVICES: loading credentials", flush=True)
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        print(f"GET_SERVICES: creds valid={creds.valid}, expired={creds.expired}", flush=True)

    if creds and creds.expired and creds.refresh_token:
        print("GET_SERVICES: refreshing token", flush=True)
        creds.refresh(Request())
        print("GET_SERVICES: token refreshed successfully", flush=True)
        if token_path == 'token.json':
            with open(token_path, 'w') as token:
                token.write(creds.to_json())

    if not creds or not creds.valid:
        print(f"GET_SERVICES: creds invalid — creds={creds}, valid={creds.valid if creds else 'N/A'}", flush=True)
        raise Exception(
            "OAuth token missing or invalid. "
            "Run python authorize.py to re-authenticate."
        )

    print("GET_SERVICES: building services", flush=True)
    docs_service = build('docs', 'v1', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)
    print("GET_SERVICES: done", flush=True)
    return docs_service, drive_service


def create_and_share_doc(title: str, sections: dict, issues: list, recipient_email: str) -> str:
    print("STEP 1: entering create_and_share_doc", flush=True)

    docs_service, drive_service = get_services()
    print("STEP 2: got services", flush=True)

    doc = docs_service.documents().create(body={'title': title}).execute()
    print(f"STEP 3: created doc {doc['documentId']}", flush=True)
    doc_id = doc['documentId']

    drive_service.files().update(
        fileId=doc_id,
        addParents=FOLDER_ID,
        removeParents='root',
        fields='id, parents'
    ).execute()
    print("STEP 4: moved to folder", flush=True)

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

    print("STEP 5: sending batchUpdate", flush=True)
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={'requests': requests}
    ).execute()
    print("STEP 6: batchUpdate done", flush=True)

    drive_service.permissions().create(
        fileId=doc_id,
        body={
            'type': 'user',
            'role': 'writer',
            'emailAddress': recipient_email,
        },
        sendNotificationEmail=True,
    ).execute()
    print("STEP 7: shared with user", flush=True)

    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"STEP 8: returning url {doc_url}", flush=True)
    return doc_url