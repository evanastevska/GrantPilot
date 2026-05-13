import os
import queue
from dotenv import load_dotenv
from google import genai
from google.genai import types
from tools import read_url
from docs_api import create_and_share_doc

load_dotenv()
client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

CINEMA_VERDE_CONTEXT = """
Cinema Verde is a 501(c)(3) nonprofit environmental film festival based in
Gainesville, Florida. Mission: environmental education and advocacy through
the art of film. Programs include an annual film festival, year-round
screenings, environmental education initiatives, and community partnerships
with local schools and conservation groups in North Central Florida.
Website: cinemaverde.org. Small all-volunteer team, no dedicated grant writer.
"""

GRANT_SECTIONS = [
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

SYSTEM_PROMPT = f"""You are an expert grant writer working on behalf of Cinema Verde.

{CINEMA_VERDE_CONTEXT}

Your job is to research the grant opportunity the user provides and write a complete,
compelling grant application tailored specifically to this funder.

Follow this process:
1. Use Google Search and read_url to research the funder thoroughly —
   their priorities, past grantees, funding amounts, deadlines, and eligibility.
2. Flag any issues using flag_issue — for example if the funder only gives to
   organizations in a specific state, or has a focus that doesn't match Cinema Verde.
3. Write each section using write_section, in order. Tailor every section to what
   you learned about this specific funder. Do not write generic grant boilerplate.
4. The Notes for Reviewer section should list specific things the human needs to
   verify, add, or customize — dollar amounts, statistics, contact names, etc.
5. When all sections are written, call finish.

Be thorough in your research before writing.
"""

#tool declarations: tells gemini what is is and its parameters

read_url_declaration = types.FunctionDeclaration(
    name="read_url",
    description="Fetch and read the text content of a webpage. Use this to read funder websites, grant guidelines, or any URL.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "url": types.Schema(
                type=types.Type.STRING,
                description="The full URL to fetch, including https://"
            )
        },
        required=["url"]
    )
)

write_section_declaration = types.FunctionDeclaration(
    name="write_section",
    description="Write a section of the grant application. Call this once per section after you have enough information.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "section_name": types.Schema(
                type=types.Type.STRING,
                description=f"Name of the section. Must be one of: {', '.join(GRANT_SECTIONS)}"
            ),
            "content": types.Schema(
                type=types.Type.STRING,
                description="Full text content of this grant section, written professionally and tailored to this funder."
            )
        },
        required=["section_name", "content"]
    )
)

flag_issue_declaration = types.FunctionDeclaration(
    name="flag_issue",
    description="Flag a potential problem or mismatch between Cinema Verde and this grant opportunity.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "issue": types.Schema(
                type=types.Type.STRING,
                description="A clear description of the concern."
            )
        },
        required=["issue"]
    )
)

finish_declaration = types.FunctionDeclaration(
    name="finish",
    description="Call this when you have written all grant sections and are ready to compile the final document.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={}
    )
)

custom_tools = types.Tool(function_declarations=[
    read_url_declaration,
    write_section_declaration,
    flag_issue_declaration,
    finish_declaration,
])

google_search_tool = types.Tool(
    google_search=types.GoogleSearch()
)


#main agent function

def run_agent(grant_input: str, recipient_email: str, q: queue.Queue):
    sections = {}
    issues = []

    try:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[custom_tools, google_search_tool],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="AUTO",
                ),
                include_server_side_tool_invocations=True,
            )
        )

        conversation_history = [
            types.Content(
                role="user",
                parts=[types.Part(text=f"Here is the grant opportunity to research and write for:\n\n{grant_input}")]
            )
        ]

        q.put("Starting research on grant opportunity...")

        MAX_ITERATIONS = 30
        iteration = 0

        #langchain would replace this
        while iteration < MAX_ITERATIONS:
            iteration += 1

            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=conversation_history,
                config=config,
            )

            #add model response to history
            conversation_history.append(response.candidates[0].content)

            #collect tool calls from response
            tool_calls = [
                part for part in response.candidates[0].content.parts
                if part.function_call is not None
            ]

            if not tool_calls:
                #model responded with text, so either done or confused
                q.put("Agent finished reasoning.")
                break

            #execute each tool call and collect results
            tool_results = []

            for part in tool_calls:
                fn = part.function_call
                name = fn.name
                args = dict(fn.args)

                if name == "read_url":
                    url = args["url"]
                    q.put(f"Reading: {url}")
                    result = read_url(url)
                    tool_results.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=name,
                                response={"result": result}
                            )
                        )
                    )

                elif name == "write_section":
                    section_name = args["section_name"]
                    content = args["content"]
                    sections[section_name] = content
                    q.put(f"Writing section: {section_name}")
                    tool_results.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=name,
                                response={"result": f"Section '{section_name}' written."}
                            )
                        )
                    )

                elif name == "flag_issue":
                    issue = args["issue"]
                    issues.append(issue)
                    q.put(f"Flagged: {issue}")
                    tool_results.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=name,
                                response={"result": "Issue noted."}
                            )
                        )
                    )

                elif name == "finish":
                    q.put("All sections written. Creating Google Doc...")
                    doc_url = create_and_share_doc(
                        title="Grant Application — Cinema Verde",
                        sections=sections,
                        issues=issues,
                        recipient_email=recipient_email,
                    )
                    q.put(f"DONE:{doc_url}")
                    return

            #feed all tool results back to the model
            conversation_history.append(
                types.Content(
                    role="user",
                    parts=tool_results
                )
            )

        if iteration >= MAX_ITERATIONS:
            q.put("ERROR: Agent hit maximum iterations without finishing.")

    except Exception as e:
        q.put(f"ERROR: {str(e)}")