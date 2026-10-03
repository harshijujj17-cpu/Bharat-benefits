"""Gemini-based agentic loop that decides which tools to call and when.

Public API
----------
``run_agent(profile, retriever, *, client, model_name)``
    Accepts a structured citizen profile and returns the final
    recommendation payload **plus** a list of concise status lines
    (e.g. "✓ Profile checked") for the UI to display.

Internal design
---------------
* A single Gemini ``generate_content`` call with ``tools`` declared.
* Gemini decides the order: inspect profile → maybe ask follow-up →
  retrieve → eligibility → documents.
* The loop replays tool results and lets Gemini call again until it
  emits a plain-text final answer or exhausts a hard iteration cap.
* Chain-of-thought is never exposed; only status lines are surfaced.
"""

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from rag.json_retriever import JSONSchemeRetriever


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_NAME = "gemini-3.5-pro"
FALLBACK_MODELS = ("gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash")
MAX_ITERATIONS = 8

# ── Gemini tool declarations ────────────────────────────────────────────

_TOOL_DECLARATIONS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="retrieve_schemes",
            description=(
                "Search the ChromaDB scheme collection for candidate schemes "
                "matching the citizen profile.  Call this after inspecting the "
                "profile to obtain scheme candidates."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "top_k": {
                        "type": "INTEGER",
                        "description": "Number of candidate schemes to return (default 3).",
                    },
                },
                "required": [],
            },
        ),
        types.FunctionDeclaration(
            name="check_eligibility",
            description=(
                "Run Gemini-grounded eligibility analysis for the citizen profile "
                "against a set of retrieved schemes.  Call this after retrieving "
                "schemes to produce relevance explanations and missing-information "
                "lists."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {},
                "required": [],
            },
        ),
        types.FunctionDeclaration(
            name="get_documents",
            description=(
                "Collect the list of required documents for each scheme.  "
                "Call this after eligibility has been checked."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {},
                "required": [],
            },
        ),
        types.FunctionDeclaration(
            name="ask_followup",
            description=(
                "Ask the citizen a clarifying question when the profile is "
                "missing information that is critical for scheme retrieval "
                "(e.g. state, occupation, income).  The question text is returned "
                "to the user.  Only use this when absolutely necessary."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "question": {
                        "type": "STRING",
                        "description": "The follow-up question to present to the citizen.",
                    },
                },
                "required": ["question"],
            },
        ),
    ],
)

# ── System prompt ────────────────────────────────────────────────────────

_AGENT_SYSTEM_INSTRUCTION = """\
You are an internal scheme-recommendation agent.  You receive a structured
citizen profile and must decide which tools to call, in what order, to produce
a final scheme recommendation.

Workflow:
1. Inspect the profile.  If critical fields (state, occupation, income) are
   empty or ambiguous, call ``ask_followup`` with a single clarifying question.
2. Call ``retrieve_schemes`` to get candidate schemes from ChromaDB.
3. If retrieval returns zero useful schemes, retry ``retrieve_schemes`` ONCE
   with a higher top_k (e.g. 5).  If still empty, produce a polite "no
   schemes found" final answer.
4. Call ``check_eligibility`` to get grounded explanations.
5. Call ``get_documents`` to collect required-document lists.
6. Produce your final answer as a plain-text JSON object with key
   ``"final_recommendation"`` containing the combined result.

Rules:
- Never expose your reasoning or chain-of-thought to the user.
- Do NOT fabricate scheme data.  Use only the data returned by tools.
- Do NOT call the same tool more than twice.
- Do NOT skip the eligibility step.
- After the tools have run, return a single JSON block as your final answer.
""".strip()


# ── Helper: build a Gemini client ────────────────────────────────────────

def _get_client(client: Any | None = None) -> Any:
    if client is not None:
        return client
    from agent.secrets import get_api_key
    return genai.Client(api_key=get_api_key())


# ── Tool dispatcher ─────────────────────────────────────────────────────

def _dispatch_tool(
    fn_name: str,
    fn_args: dict[str, Any],
    *,
    profile: dict[str, Any],
    retriever: JSONSchemeRetriever,
    state: dict[str, Any],
    status: list[str],
    gemini_client: Any,
    model_name: str | None,
) -> dict[str, Any]:
    """Execute a tool by name and return its JSON-serialisable result."""

    from agent.tools import retrieve_schemes, check_eligibility, get_documents

    if fn_name == "retrieve_schemes":
        top_k = fn_args.get("top_k", 3)
        result = retrieve_schemes(profile, retriever, top_k=top_k)
        state["retrieved_schemes"] = result["schemes"]
        status.append("✓ Schemes retrieved")
        return result

    if fn_name == "check_eligibility":
        schemes = state.get("retrieved_schemes", [])
        if not schemes:
            return {"error": "No schemes retrieved yet.  Call retrieve_schemes first."}
        result = check_eligibility(
            profile, schemes, client=gemini_client, model_name=model_name,
        )
        state["eligibility_result"] = result
        status.append("✓ Eligibility checked")
        return result

    if fn_name == "get_documents":
        schemes = state.get("retrieved_schemes", [])
        if not schemes:
            return {"error": "No schemes retrieved yet.  Call retrieve_schemes first."}
        result = get_documents(schemes)
        state["documents"] = result
        status.append("✓ Documents collected")
        return result

    if fn_name == "ask_followup":
        question = fn_args.get("question", "Could you provide more details?")
        state["followup_question"] = question
        status.append("⟳ Follow-up needed")
        return {"question": question, "status": "waiting_for_user"}

    return {"error": f"Unknown tool: {fn_name}"}


# ── Public API ───────────────────────────────────────────────────────────

class AgentResult:
    """Immutable result container returned by ``run_agent``."""

    __slots__ = (
        "recommendation", "status_lines", "followup_question", "raw_state",
    )

    def __init__(
        self,
        recommendation: dict[str, Any] | None,
        status_lines: list[str],
        followup_question: str | None,
        raw_state: dict[str, Any],
    ) -> None:
        self.recommendation = recommendation
        self.status_lines = status_lines
        self.followup_question = followup_question
        self.raw_state = raw_state

    @property
    def needs_followup(self) -> bool:
        return self.followup_question is not None

    @property
    def has_recommendation(self) -> bool:
        return self.recommendation is not None


def run_agent(
    profile: dict[str, Any],
    retriever: JSONSchemeRetriever,
    *,
    client: Any | None = None,
    model_name: str | None = None,
) -> AgentResult:
    """Run the agentic loop and return an ``AgentResult``.

    Parameters
    ----------
    profile : dict
        Structured citizen profile built from the form.
    retriever : SchemeRetriever
        An initialised ``SchemeRetriever`` instance (ChromaDB).
    client : optional
        Pre-built ``genai.Client``.  Created from env if ``None``.
    model_name : optional
        Override for the Gemini model name.

    Returns
    -------
    AgentResult
        Contains ``.recommendation``, ``.status_lines``,
        ``.followup_question``, and ``.raw_state``.
    """
    gemini_client = _get_client(client)
    chosen_model = model_name or os.getenv("GEMINI_MODEL", DEFAULT_MODEL_NAME)

    status: list[str] = []
    state: dict[str, Any] = {}

    status.append("✓ Profile checked")

    # Initial user message handed to Gemini
    user_message = json.dumps(
        {"citizen_profile": profile},
        ensure_ascii=False,
        sort_keys=True,
    )

    contents: list[types.Content] = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)],
        ),
    ]

    for _iteration in range(MAX_ITERATIONS):
        # Call Gemini with tool declarations
        response = _generate_with_fallback(
            gemini_client, chosen_model, contents, status,
        )

        # Check if Gemini wants to call tools
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None:
            break

        parts = candidate.content.parts if candidate.content else []
        function_calls = [p for p in parts if p.function_call]

        # No tool calls → Gemini produced a final text answer
        if not function_calls:
            final_text = response.text or ""
            recommendation = _parse_final_answer(final_text, state)
            return AgentResult(
                recommendation=recommendation,
                status_lines=status,
                followup_question=state.get("followup_question"),
                raw_state=state,
            )

        # Append the model's tool-call turn to the conversation
        contents.append(candidate.content)

        # Execute each tool call and build function-response parts
        fn_response_parts: list[types.Part] = []
        for part in function_calls:
            fc = part.function_call
            result = _dispatch_tool(
                fc.name,
                dict(fc.args) if fc.args else {},
                profile=profile,
                retriever=retriever,
                state=state,
                status=status,
                gemini_client=gemini_client,
                model_name=model_name,
            )

            # If the agent asked a follow-up, short-circuit
            if fc.name == "ask_followup":
                return AgentResult(
                    recommendation=None,
                    status_lines=status,
                    followup_question=result.get("question"),
                    raw_state=state,
                )

            fn_response_parts.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response=_ensure_serialisable(result),
                )
            )

        contents.append(
            types.Content(role="user", parts=fn_response_parts),
        )

    # Exhausted iterations – return whatever we have
    recommendation = state.get("eligibility_result")
    if recommendation is None and state.get("retrieved_schemes"):
        status.append("⚠ Agent reached iteration limit")
    return AgentResult(
        recommendation=recommendation,
        status_lines=status,
        followup_question=state.get("followup_question"),
        raw_state=state,
    )


# ── Internal helpers ─────────────────────────────────────────────────────

def _generate_with_fallback(
    client: Any,
    primary_model: str,
    contents: list[types.Content],
    status: list[str],
) -> Any:
    """Try the primary model, then fallbacks."""
    candidate_models = [primary_model] + [
        m for m in FALLBACK_MODELS if m != primary_model
    ]
    last_error: Exception | None = None
    for model in candidate_models:
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=_AGENT_SYSTEM_INSTRUCTION,
                    tools=[_TOOL_DECLARATIONS],
                    temperature=0.1,
                ),
            )
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("All Gemini models failed.")


def _parse_final_answer(
    text: str, state: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract the recommendation from Gemini's final text answer.

    Gemini is instructed to return JSON with a ``final_recommendation``
    key.  If it does, we merge it with the eligibility result already in
    state.  Otherwise we fall back to the raw eligibility result.
    """
    # Prefer the structured eligibility result produced by check_eligibility
    eligibility = state.get("eligibility_result")
    documents = state.get("documents")

    if eligibility is not None:
        # Merge document info into each recommendation if available
        if documents and "document_requirements" in documents:
            doc_map = {
                d["scheme_name"]: d["required_documents"]
                for d in documents["document_requirements"]
            }
            for rec in eligibility.get("recommendations", []):
                if rec["scheme_name"] in doc_map:
                    rec.setdefault("required_documents", doc_map[rec["scheme_name"]])
        return eligibility

    # Try parsing Gemini's text as JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed.get("final_recommendation", parsed)
    except (json.JSONDecodeError, TypeError):
        pass

    return None


def _ensure_serialisable(obj: Any) -> dict[str, Any]:
    """Guarantee the value is a dict Gemini can consume as a tool response."""
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    return {"result": str(obj)}


def _make_json_safe(value: Any) -> Any:
    """Recursively convert values that aren't JSON-native."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, dict):
        return {k: _make_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_make_json_safe(item) for item in value]
    return str(value)
