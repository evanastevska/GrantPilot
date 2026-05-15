import os
import datetime
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

SECTION_ORDER = [
    "Executive Summary",
    "Organization Background",
    "Statement of Need",
    "Project Description",
    "Goals and Objectives",
    "Evaluation Plan",
    "Budget Narrative",
    "Conclusion",
    "Notes for Reviewer",
]


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


def pt(points):
    return {'magnitude': points, 'unit': 'PT'}


def insert_text(requests, index, text):
    requests.append({
        'insertText': {
            'location': {'index': index},
            'text': text,
        }
    })


def set_paragraph_style(requests, start, end, named_style=None, alignment=None,
                        space_above=None, space_below=None, line_spacing=None):
    style = {}
    fields = []
    if named_style:
        style['namedStyleType'] = named_style
        fields.append('namedStyleType')
    if alignment:
        style['alignment'] = alignment
        fields.append('alignment')
    if space_above is not None:
        style['spaceAbove'] = pt(space_above)
        fields.append('spaceAbove')
    if space_below is not None:
        style['spaceBelow'] = pt(space_below)
        fields.append('spaceBelow')
    if line_spacing is not None:
        style['lineSpacing'] = line_spacing
        fields.append('lineSpacing')
    requests.append({
        'updateParagraphStyle': {
            'range': {'startIndex': start, 'endIndex': end},
            'paragraphStyle': style,
            'fields': ','.join(fields),
        }
    })


def set_text_style(requests, start, end, bold=False, italic=False,
                   font_size=None, font_family=None, foreground_color=None):
    style = {}
    fields = []
    if bold:
        style['bold'] = True
        fields.append('bold')
    if italic:
        style['italic'] = True
        fields.append('italic')
    if font_size:
        style['fontSize'] = {'magnitude': font_size, 'unit': 'PT'}
        fields.append('fontSize')
    if font_family:
        style['weightedFontFamily'] = {'fontFamily': font_family}
        fields.append('weightedFontFamily')
    if foreground_color:
        r, g, b = foreground_color
        style['foregroundColor'] = {
            'color': {'rgbColor': {'red': r/255, 'green': g/255, 'blue': b/255}}
        }
        fields.append('foregroundColor')
    requests.append({
        'updateTextStyle': {
            'range': {'startIndex': start, 'endIndex': end},
            'textStyle': style,
            'fields': ','.join(fields),
        }
    })


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
    idx = 1
    date_str = datetime.date.today().strftime("%B %Y")


    org_line = "Cinema Verde  ·  Gainesville, Florida\n"
    insert_text(requests, idx, org_line)
    set_paragraph_style(requests, idx, idx + len(org_line), alignment='CENTER', space_below=2)
    set_text_style(requests, idx, idx + len(org_line) - 1,
                   font_family='Arial', font_size=9, foreground_color=(120, 110, 140))
    idx += len(org_line)

    main_title = "Grant Application\n"
    insert_text(requests, idx, main_title)
    set_paragraph_style(requests, idx, idx + len(main_title),
                        named_style='TITLE', alignment='CENTER', space_below=4)
    idx += len(main_title)

    subtitle = "Prepared for Review\n"
    insert_text(requests, idx, subtitle)
    set_paragraph_style(requests, idx, idx + len(subtitle),
                        named_style='SUBTITLE', alignment='CENTER', space_below=16)
    idx += len(subtitle)

    meta_line = f"Date: {date_str}     ·     Contact: info@cinemaverde.org\n"
    insert_text(requests, idx, meta_line)
    set_paragraph_style(requests, idx, idx + len(meta_line),
                        alignment='CENTER', space_below=6)
    set_text_style(requests, idx, idx + len(meta_line) - 1,
                   font_family='Arial', font_size=10, foreground_color=(120, 110, 140))
    idx += len(meta_line)

    divider = "————————————————————————————————\n\n"
    insert_text(requests, idx, divider)
    set_paragraph_style(requests, idx, idx + len(divider),
                        alignment='CENTER', space_below=8)
    set_text_style(requests, idx, idx + len(divider) - 2,
                   font_family='Arial', font_size=10, foreground_color=(200, 190, 220))
    idx += len(divider)

    if issues:
        issues_heading = "⚑  Internal Notes — Do Not Submit\n"
        insert_text(requests, idx, issues_heading)
        set_paragraph_style(requests, idx, idx + len(issues_heading),
                            space_above=0, space_below=4)
        set_text_style(requests, idx, idx + len(issues_heading) - 1,
                       bold=True, font_family='Arial', font_size=10,
                       foreground_color=(160, 80, 20))
        idx += len(issues_heading)

        for issue in issues:
            issue_line = f"·  {issue}\n"
            insert_text(requests, idx, issue_line)
            set_paragraph_style(requests, idx, idx + len(issue_line),
                                space_below=2, line_spacing=130)
            set_text_style(requests, idx, idx + len(issue_line) - 1,
                           font_family='Arial', font_size=10,
                           foreground_color=(140, 70, 10))
            idx += len(issue_line)

        spacer = "\n"
        insert_text(requests, idx, spacer)
        idx += len(spacer)

    for section_num, section_name in enumerate(SECTION_ORDER, start=1):
        content = sections.get(section_name, "[Section not written]")
        is_notes = section_name == "Notes for Reviewer"

        # Section heading
        heading_text = f"{section_num:02d}  {section_name.upper()}\n"
        insert_text(requests, idx, heading_text)
        set_paragraph_style(requests, idx, idx + len(heading_text),
                            named_style='HEADING_2',
                            space_above=18, space_below=6)

        if is_notes:
            set_text_style(requests, idx, idx + len(heading_text) - 1,
                           font_family='Arial', font_size=10,
                           foreground_color=(100, 90, 130))
        else:
            set_text_style(requests, idx, idx + len(heading_text) - 1,
                           font_family='Arial', font_size=10,
                           foreground_color=(60, 40, 100))

        idx += len(heading_text)

        paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
        if not paragraphs:
            paragraphs = [content]

        for para_num, para in enumerate(paragraphs):
            para_text = para + "\n"
            insert_text(requests, idx, para_text)

            space_above = 0 if para_num > 0 else 2
            set_paragraph_style(requests, idx, idx + len(para_text),
                                space_above=space_above, space_below=6,
                                line_spacing=138)

            if is_notes:
                set_text_style(requests, idx, idx + len(para_text) - 1,
                               italic=True, font_family='Arial', font_size=11,
                               foreground_color=(100, 90, 130))
            elif para_num == 0 and section_name == "Executive Summary":
                set_text_style(requests, idx, idx + len(para_text) - 1,
                               bold=True, font_family='Georgia', font_size=11)
            else:
                set_text_style(requests, idx, idx + len(para_text) - 1,
                               font_family='Georgia', font_size=11)

            idx += len(para_text)

        gap = "\n"
        insert_text(requests, idx, gap)
        idx += len(gap)

    footer = f"\nCinema Verde  ·  Grant Application  ·  {date_str}"
    insert_text(requests, idx, footer)
    set_paragraph_style(requests, idx, idx + len(footer),
                        alignment='CENTER', space_above=12)
    set_text_style(requests, idx, idx + len(footer),
                   font_family='Arial', font_size=9,
                   foreground_color=(180, 170, 200))
    idx += len(footer)

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