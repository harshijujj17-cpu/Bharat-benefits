"""Discrete tool functions the agent can invoke.

Each function wraps existing retrieval / recommendation logic and returns
a plain dict that can be serialised as a tool-call result.
"""

import json
from typing import Any

from agent.recommendation import recommend_schemes, FACT_FIELDS, FIELD_LABELS
from rag.json_retriever import JSONSchemeRetriever


# ---------------------------------------------------------------------------
# 1. retrieve_schemes
# ---------------------------------------------------------------------------

def retrieve_schemes(
    profile: dict[str, Any],
    retriever: JSONSchemeRetriever,
    *,
    top_k: int = 3,
) -> dict[str, Any]:
    """Retrieve candidate schemes from ChromaDB for *profile*.

    Returns
    -------
    dict
        ``{"schemes": [...], "count": int}``
    """
    schemes = retriever.retrieve_schemes(profile, top_k=top_k)
    return {
        "schemes": schemes,
        "count": len(schemes),
    }


# ---------------------------------------------------------------------------
# 2. check_eligibility
# ---------------------------------------------------------------------------

def check_eligibility(
    profile: dict[str, Any],
    schemes: list[dict[str, Any]],
    *,
    client: Any | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Run the Gemini grounded-recommendation step for *profile* × *schemes*.

    Delegates to the existing ``recommend_schemes`` function and returns
    its output verbatim so no logic is duplicated.
    """
    return recommend_schemes(
        profile,
        schemes,
        client=client,
        model_name=model_name,
    )


# ---------------------------------------------------------------------------
# 3. get_documents
# ---------------------------------------------------------------------------

def get_documents(schemes: list[dict[str, Any]]) -> dict[str, Any]:
    """Collect required-document lists from the already-retrieved schemes.

    This is a lightweight extraction — no extra API calls.  When a scheme
    record lacks the ``required_documents`` field the entry is still
    included with an explicit "not available" note.
    """
    docs: list[dict[str, Any]] = []
    for scheme in schemes:
        name = scheme.get("scheme_name", "Unknown")
        raw = scheme.get("required_documents")
        if raw and raw != []:
            docs.append({"scheme_name": name, "required_documents": raw})
        else:
            docs.append({
                "scheme_name": name,
                "required_documents": "Not available in scheme data.",
            })
    return {"document_requirements": docs}


# ---------------------------------------------------------------------------
# Tool registry – used by the agent loop to dispatch calls
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, callable] = {
    "retrieve_schemes": retrieve_schemes,
    "check_eligibility": check_eligibility,
    "get_documents": get_documents,
}
