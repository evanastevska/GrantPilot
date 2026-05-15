import os
import queue
import time
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
   Keep each section focused and concise — 200 to 300 words maximum.
5. The Notes for Reviewer section should list specific things the human needs to
   verify, add, or customize — dollar amounts, statistics, contact names, etc.
6. When all sections are written, call finish.

Be thorough in your research before writing. Search first, read the relevant pages,
then write.
"""

#tool declarations: what is it and parameters

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
    description=(
        "Write a section of the grant application. Call this once per section after "
        "you have enough information. Keep each section concise: 200–300 words maximum. "
        "Do not pad or repeat information across sections."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "section_name": types.Schema(
                type=types.Type.STRING,
                description=f"Name of the section. Must be one of: {', '.join(GRANT_SECTIONS)}"
            ),
            "content": types.Schema(
                type=types.Type.STRING,
                description=(
                    "The section content, written professionally and tailored to this funder. "
                    "Maximum 300 words. Be specific and compelling, not generic."
                )
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


def _is_research_turn(content: types.Content) -> bool:
    """Return True if this history entry is a search/read_url tool call or its result.

    We identify these by checking model turns that only contain search_web or
    read_url function calls, and user turns that only contain function_response
    parts for those same tools. Written sections and flag_issue results are
    kept because they're compact and contextually useful.
    """
    if content.parts is None:
        return False

    RESEARCH_TOOLS = {"search_web", "read_url"}

    #model turn: all parts are function_calls for research tools
    if content.role == "model":
        calls = [p for p in content.parts if p.function_call is not None]
        non_calls = [p for p in content.parts if p.function_call is None and (p.text or "") != ""]
        if calls and not non_calls:
            return all(p.function_call.name in RESEARCH_TOOLS for p in calls)

    #user turn: all parts are function_responses for research tools
    if content.role == "user":
        responses = [p for p in content.parts if p.function_response is not None]
        non_responses = [p for p in content.parts if p.function_response is None and (p.text or "") != ""]
        if responses and not non_responses:
            return all(p.function_response.name in RESEARCH_TOOLS for p in responses)

    return False


def _prune_history(history: list, sections: dict) -> list:
    """Drop research turns (search/read_url pairs) from history.

    Called once writing begins. The first entry (the original user prompt)
    is always kept. A compact research summary is injected so the model
    retains awareness of what was found without the full token cost.
    """
    #always keep index 0 (the original user prompt)
    pruned = [history[0]]

    #one line summary of what sections have been written so far
    written = list(sections.keys())
    remaining = [s for s in GRANT_SECTIONS if s not in written]

    summary_lines = ["[Research phase complete. Raw search and URL results have been summarised to save context.]"]
    if written:
        summary_lines.append(f"Sections already written: {', '.join(written)}.")
    if remaining:
        summary_lines.append(f"Sections still to write: {', '.join(remaining)}.")
    summary_lines.append("Continue writing the remaining sections using write_section, then call finish.")

    pruned.append(
        types.Content(
            role="user",
            parts=[types.Part(text="\n".join(summary_lines))]
        )
    )

    #keep non-research turns (write_section calls, flag_issue calls, their results, and any nudge messages)
    for entry in history[1:]:
        if not _is_research_turn(entry):
            pruned.append(entry)

    return pruned


#main agent function

def run_agent(grant_input: str, recipient_email: str, q: queue.Queue, grant_url: str = ""):
    sections = {}
    issues = []
    history_pruned = False  # only prune once

    try:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[custom_tools],
            max_output_tokens=16384,
        )

        #build the opening user message. if URL was provided, fetch it
        opening_parts = []

        if grant_url:
            q.put(f"Reading grant URL: {grant_url}")
            url_content = read_url(grant_url)
            opening_parts.append(
                f"I have pre-fetched the grant guidelines from {grant_url}:\n\n"
                f"{url_content}\n\n"
                f"---"
            )

        if grant_input:
            opening_parts.append(
                f"Additional context provided by the user:\n\n{grant_input}"
            )

        if not opening_parts:
            opening_parts.append("No grant details provided.")

        opening_text = "\n\n".join(opening_parts)
        opening_text = "Here is the grant opportunity to research and write for:\n\n" + opening_text

        conversation_history = [
            types.Content(
                role="user",
                parts=[types.Part(text=opening_text)]
            )
        ]

        q.put("Starting research on grant opportunity...")

        MAX_ITERATIONS = 30
        iteration = 0

        while iteration < MAX_ITERATIONS:
            iteration += 1

            #retrying on 503 (server overload) up to 3 times
            for attempt in range(3):
                try:
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=conversation_history,
                        config=config,
                    )
                    break  #success
                except Exception as api_err:
                    if '503' in str(api_err) and attempt < 2:
                        wait = 15 * (attempt + 1)  # 15s, then 30s
                        q.put(f"Model busy (503), retrying in {wait}s...")
                        time.sleep(wait)
                    else:
                        raise  #not a 503, or out of retries, let outer handler catch it

            #add model response to history
            candidate = response.candidates[0]

            if candidate.content is None or candidate.content.parts is None:
                finish_reason = candidate.finish_reason

                if str(finish_reason) == 'FinishReason.MALFORMED_FUNCTION_CALL' or 'MALFORMED_FUNCTION_CALL' in str(finish_reason):
                    q.put("Retrying last step (malformed response)...")

                    if not history_pruned:
                        q.put("Pruning research history to free up context...")
                        conversation_history = _prune_history(conversation_history, sections)
                        history_pruned = True
                    else:
                        written = list(sections.keys())
                        remaining = [s for s in GRANT_SECTIONS if s not in written]
                        nudge = (
                            f"Sections written so far: {', '.join(written) if written else 'none'}. "
                            f"Please write the next section: '{remaining[0] if remaining else 'all done — call finish'}'. "
                            "Keep it under 300 words and call write_section now."
                        )
                        conversation_history.append(
                            types.Content(
                                role="user",
                                parts=[types.Part(text=nudge)]
                            )
                        )
                    continue

                q.put(f"ERROR: Model returned no content. Finish reason: {finish_reason}")
                return

            #anly reaches here if content is not None
            conversation_history.append(candidate.content)

            tool_calls = [
                part for part in (candidate.content.parts or [])
                if part.function_call is not None
            ]

            #prune history the first time we see a write_section call before the history has a chance to grow further
            if not history_pruned:
                for part in tool_calls:
                    if part.function_call.name == "write_section":
                        q.put("Research complete — pruning history before writing sections...")
                        conversation_history = _prune_history(conversation_history, sections)
                        history_pruned = True
                        break

            if not tool_calls:
                text_parts = [
                    part.text for part in candidate.content.parts
                    if part.text is not None
                ]

                if text_parts:
                    q.put("Retrying...")
                    written = list(sections.keys())
                    remaining = [s for s in GRANT_SECTIONS if s not in written]
                    nudge = (
                        "Please continue by calling the appropriate tools. "
                        f"Sections written: {', '.join(written) if written else 'none'}. "
                        f"Next section to write: '{remaining[0] if remaining else 'all done — call finish'}'. "
                        "Use write_section now, keeping content under 300 words."
                    )
                    conversation_history.append(
                        types.Content(
                            role="user",
                            parts=[types.Part(text=nudge)]
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