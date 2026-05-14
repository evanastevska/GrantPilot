import os
import queue
from dotenv import load_dotenv
from google import genai
from google.genai import types
from tools import read_url
from docs_api import create_and_share_doc
from tools import read_url, search_web
import traceback

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
1. Use search_web to research the funder — their priorities, past grantees, funding
   amounts, deadlines, and eligibility requirements. Search multiple times if needed.
2. Use read_url to read specific pages you find — grant guidelines, about pages,
   past grantee lists. Always read cinemaverde.org as well.
3. Flag any eligibility issues using flag_issue — geographic restrictions, budget
   requirements, focus areas that don't match Cinema Verde.
4. Write each section using write_section, in order. Tailor every section to what
   you learned about this specific funder. Do not write generic grant boilerplate.
5. The Notes for Reviewer section should list specific things the human needs to
   verify, add, or customize — dollar amounts, statistics, contact names, etc.
6. When all sections are written, call finish.

Be thorough in your research before writing. Search first, read the relevant pages,
then write.
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

search_web_declaration = types.FunctionDeclaration(
    name="search_web",
    description="Search the web for information about a funder, grant program, or any research needed to write the grant. Use this first before read_url to find relevant URLs and background information.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="The search query. Be specific — include the funder name, grant program name, and what you're looking for."
            )
        },
        required=["query"]
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
    search_web_declaration,
    read_url_declaration,
    write_section_declaration,
    flag_issue_declaration,
    finish_declaration,
])



#main agent function

def run_agent(grant_input: str, recipient_email: str, q: queue.Queue):
    sections = {}
    issues = []

    try:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[custom_tools],
            max_output_tokens=8192,
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
                model="gemini-2.5-flash",
                contents=conversation_history,
                config=config,
            )

            #add model response to history
            conversation_history.append(response.candidates[0].content)

            #collect tool calls from response
            candidate = response.candidates[0]

            if candidate.content is None:
                finish_reason = candidate.finish_reason

                if str(finish_reason) == 'MALFORMED_FUNCTION_CALL':
                    #tell the model what happened and ask it to continue
                    q.put("Retrying last step...")
                    conversation_history.append(
                        types.Content(
                            role="user",
                            parts=[types.Part(text="Your last response was malformed. Please check which sections have been written so far and continue writing any remaining sections, keeping each section concise.")]
                        )
                    )
                    continue  #goes back to top of while loop

                q.put(f"ERROR: Model returned no content. Finish reason: {finish_reason}")
                return

            #temporary debug, print raw response text
            try:
                for part in response.candidates[0].content.parts:
                    print("PART TYPE:", type(part))
                    print("PART:", part)
            except Exception as debug_err:
                print("DEBUG ERROR:", debug_err)

            tool_calls = [
                part for part in candidate.content.parts
                if part.function_call is not None
            ]

            if not tool_calls:
                #check if there's a text response
                text_parts = [
                    part.text for part in candidate.content.parts
                    if part.text is not None
                ]

                if text_parts:
                    #model gave a text response instead of a tool call
                    #nudge it back to using tools
                    q.put("Retrying...")
                    conversation_history.append(
                        types.Content(
                            role="user",
                            parts=[types.Part(text="Please continue by calling the appropriate tools. Use write_section to write any remaining sections, then call finish when all sections are complete.")]
                        )
                    )
                    continue
                else:
                    q.put("Agent finished reasoning.")
                    break

            #execute each tool call and collect results
            tool_results = []

            for part in tool_calls:
                fn = part.function_call
                name = fn.name
                args = dict(fn.args)

                if name == "search_web":
                    query = args["query"]
                    q.put(f"Searching: {query}")
                    result = search_web(query)
                    # trim to prevent context bloat
                    words = result.split()
                    if len(words) > 300:
                        result = ' '.join(words[:300]) + '\n[truncated]'
                    tool_results.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=name,
                                response={"result": result}
                            )
                        )
                    )

                elif name == "read_url":
                    url = args["url"]
                    q.put(f"Reading: {url}")
                    result = read_url(url)
                    #already truncated to 3000 words in tools.py, reduce further
                    words = result.split()
                    if len(words) > 1000:
                        result = ' '.join(words[:1000]) + '\n[truncated]'
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
                    try:
                        doc_url = create_and_share_doc(
                            title="Grant Application — Cinema Verde",
                            sections=sections,
                            issues=issues,
                            recipient_email=recipient_email,
                        )
                        q.put(f"DONE:{doc_url}")
                    except Exception as doc_error:
                        import traceback
                        full_error = traceback.format_exc()
                        print(full_error, flush=True)
                        q.put(f"ERROR: {repr(doc_error)}")
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
        full_error = traceback.format_exc()
        print(full_error, flush=True)
        q.put(f"ERROR: {repr(e)}")