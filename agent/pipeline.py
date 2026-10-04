"""Request-time recommendation pipeline: live search → extract → eligibility."""

from typing import Any

from agent.eligibility_match import attach_scores
from agent.profile_normalize import normalize_profile
from agent.recommendation import recommend_schemes
from rag.live_retriever import LiveSchemeRetriever, LiveSearchError

NO_RESULTS_NOTICE = (
    "No relevant government schemes were found from live official sources for this profile. "
    "Try adding more details such as occupation, gender, or education, or search with a more specific query."
)


def _public_scheme(scheme: dict[str, Any]) -> dict[str, Any]:
    blocked = {"_match_score"}
    return {key: value for key, value in scheme.items() if key not in blocked}


def recommend_for_profile(
    profile: dict[str, Any],
    *,
    retriever: LiveSchemeRetriever | None = None,
    client: Any | None = None,
    top_k: int = 8,
    include_llm_queries: bool = True,
) -> dict[str, Any]:
    profile = normalize_profile(profile)
    retriever = retriever or LiveSchemeRetriever()
    pack = retriever.retrieve_pack(
        profile,
        top_k=top_k,
        client=client,
        include_llm_queries=include_llm_queries,
    )
    retrieval = pack.metadata()
    if not pack.schemes:
        return {
            "recommendations": [],
            "notice": NO_RESULTS_NOTICE,
            "retrieval": retrieval,
        }

    scored = attach_scores(profile, pack.schemes)
    eligibility = recommend_schemes(profile, scored, client=client)
    recommendations = []
    for item in eligibility.get("recommendations", []):
        status = str(item.get("eligibility_status") or "cannot_confirm")
        if status == "not_relevant":
            continue
        if not item.get("official_source_url") and not item.get("official_source"):
            continue
        item["eligibility_status"] = status
        if status == "cannot_confirm":
            missing = list(item.get("missing_information") or [])
            note = "Eligibility cannot be confirmed from the live source text and the provided profile."
            if note not in missing:
                missing.append(note)
            item["missing_information"] = missing
        recommendations.append(_public_scheme(item))

    notice = None
    if not recommendations:
        notice = NO_RESULTS_NOTICE
    return {
        "recommendations": recommendations,
        "notice": notice,
        "retrieval": retrieval,
        "status_lines": [
            "Profile checked",
            "Live web search completed",
            "Official sources prioritized",
            "Eligibility compared to profile",
        ],
    }


def search_schemes(
    query: str,
    *,
    retriever: LiveSchemeRetriever | None = None,
    client: Any | None = None,
    top_k: int = 8,
) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        raise ValueError("Search query must not be empty.")
    retriever = retriever or LiveSchemeRetriever()
    pack = retriever.retrieve_pack(
        {"other_relevant_information": query},
        top_k=top_k,
        query=query,
        client=client,
        include_llm_queries=False,
    )
    retrieval = pack.metadata()
    schemes = []
    for scheme in pack.schemes:
        if not scheme.get("official_source_url"):
            continue
        schemes.append(_public_scheme(scheme))
    notice = None if schemes else (
        "No matching government schemes were found from live search for this query."
    )
    return {
        "query": query,
        "schemes": schemes,
        "notice": notice,
        "retrieval": retrieval,
    }


__all__ = ["recommend_for_profile", "search_schemes", "LiveSearchError"]
