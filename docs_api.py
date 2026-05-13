import os
from googleapiclient.discovery import build
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive',
]

FOLDER_ID = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')


def get_services():
    """Build and return authenticated Docs and Drive service clients."""
    creds = service_account.Credentials.from_service_account_file(
        'service_account.json',
        scopes=SCOPES,
    )
    docs_service = build('docs', 'v1', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return docs_service, drive_service


def create_and_share_doc(title: str, sections: dict, issues: list, recipient_email: str) -> str:
    """
    Create a Google Doc with all grant sections, save it to the
    Cinema Verde shared folder, and return the doc URL.
    """
    docs_service, drive_service = get_services()

    #create an empty Google Doc
    doc = docs_service.documents().create(body={'title': title}).execute()
    doc_id = doc['documentId']

    #build the content to insert:
    #Google Docs API writes content as a list of "requests"
    #Each request is an operation: insert text, format it, etc.
    #build the full list first, then send it in one API call

    requests = []
    current_index = 1  #Google Docs tracks position by character index, index 1 = beginning of document

    #if any flagged issues, add them at top
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

    #write each grant section in order
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

        #insert the section text
        requests.append({
            'insertText': {
                'location': {'index': current_index},
                'text': section_text
            }
        })

        #format
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

    #send all formatting requests in one batch
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={'requests': requests}
    ).execute()

    #move the doc into Cinema Verde's shared folder
    drive_service.files().update(
        fileId=doc_id,
        addParents=FOLDER_ID,
        removeParents='root',
        fields='id, parents'
    ).execute()

    #also share directly with who submitted the form
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