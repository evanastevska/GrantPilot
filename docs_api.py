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
    import os
    print("Looking for service account at:", os.path.abspath('service_account.json'))
    print("File exists:", os.path.exists('service_account.json'))

    creds = service_account.Credentials.from_service_account_file(
        'service_account.json',
        scopes=SCOPES,
    )
    print("Service account email:", creds.service_account_email)

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
    file_metadata = {
        'name': title,
        'mimeType': 'application/vnd.google-apps.document',
        'parents': [FOLDER_ID]
    }
    doc_file = drive_service.files().create(
        body=file_metadata,
        fields='id'
    ).execute()
    doc_id = doc_file['id']

    #build the content to insert:
    #Google Docs API writes content as a list of "requests"
    #each request is an operation: insert text, format it, etc.
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