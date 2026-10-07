"""Request-time live web retrieval for government schemes.

Nothing retrieved here is written to disk. Results exist only in memory
for the current request.

Includes state-relevance and need-relevance filtering so that schemes from
wrong states or unrelated domains are rejected before they become
recommendations.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from agent.model_config import get_tavily_timeout_seconds
from rag.official_sources import is_official_government_url, normalize_url, source_verification

logger = logging.getLogger(__name__)


class LiveSearchError(RuntimeError):
    """Raised when the live search provider cannot be reached or returns an error."""


# ── Indian state names for state-relevance detection ──────────────────────

INDIAN_STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya",
    "mizoram", "nagaland", "odisha", "punjab", "rajasthan", "sikkim",
    "tamil nadu", "telangana", "tripura", "uttar pradesh", "uttarakhand",
    "west bengal", "delhi", "jammu and kashmir", "ladakh", "chandigarh",
    "puducherry", "andaman and nicobar islands", "dadra and nagar haveli",
    "daman and diu", "lakshadweep",
}

# Domain suffixes/substrings that indicate a specific state
STATE_DOMAIN_HINTS: dict[str, str] = {
    "ap.gov.in": "andhra pradesh",
    "telangana.gov.in": "telangana",
    "karnataka.gov.in": "karnataka",
    "kerala.gov.in": "kerala",
    "tn.gov.in": "tamil nadu",
    "maharashtra.gov.in": "maharashtra",
    "up.gov.in": "uttar pradesh",
    "mp.gov.in": "madhya pradesh",
    "bihar.gov.in": "bihar",
    "rajasthan.gov.in": "rajasthan",
    "wb.gov.in": "west bengal",
    "gujarat.gov.in": "gujarat",
    "haryana.gov.in": "haryana",
    "odisha.gov.in": "odisha",
    "jharkhand.gov.in": "jharkhand",
    "chhattisgarh.gov.in": "chhattisgarh",
    "assam.gov.in": "assam",
    "punjab.gov.in": "punjab",
    "goa.gov.in": "goa",
    "delhi.gov.in": "delhi",
    "jk.gov.in": "jammu and kashmir",
    "himachalpradesh.gov.in": "himachal pradesh",
    "uttarakhand.gov.in": "uttarakhand",
    "manipur.gov.in": "manipur",
    "meghalaya.gov.in": "meghalaya",
    "mizoram.gov.in": "mizoram",
    "nagaland.gov.in": "nagaland",
    "sikkim.gov.in": "sikkim",
    "tripura.gov.in": "tripura",
    "arunachalpradesh.gov.in": "arunachal pradesh",
    "py.gov.in": "puducherry",
    "chandigarh.gov.in": "chandigarh",
    "ladakh.gov.in": "ladakh",
}

# Need → keyword sets for need-relevance filtering
NEED_FILTER_KEYWORDS: dict[str, set[str]] = {
    "education": {
        "education", "scholarship", "student", "school", "college", "university",
        "tuition", "fee", "post-matric", "pre-matric", "postmatric", "prematric",
        "reimbursement", "study", "academic", "degree", "vidyarthi", "shiksha",
        "learning", "stipend", "fellowship", "merit", "graduate", "undergraduate",
    },
    "agriculture": {
        "agriculture", "farmer", "farm", "crop", "kisan", "krishi", "irrigation",
        "subsidy", "seed", "fertilizer", "harvest", "ryot", "ryotu", "annadata",
        "pm-kisan", "pmkisan", "mgnrega", "land", "agri", "horticulture",
        "animal husbandry", "dairy", "fisheries", "soil",
    },
    "women & children": {
        "women", "woman", "child", "children", "girl", "maternity", "maternal",
        "pregnancy", "nutrition", "anganwadi", "icds", "mahila", "beti",
        "kanya", "stree", "nari", "ladli", "protection", "dowry",
        "domestic violence", "sukanya", "poshan",
    },
    "health": {
        "health", "medical", "hospital", "treatment", "ayushman", "insurance",
        "disease", "medicine", "doctor", "surgery", "clinic", "healthcare",
        "swasthya", "arogya",
    },
    "housing": {
        "housing", "house", "home", "shelter", "awas", "pradhan mantri awas",
        "pmay", "construction", "dwelling", "rural housing", "urban housing",
    },
    "employment": {
        "employment", "job", "skill", "training", "livelihood", "rozgar",
        "kaushal", "placement", "vocational", "apprentice", "wage",
    },
    "disability": {
        "disability", "disabled", "handicapped", "divyang", "pwd",
        "persons with disabilities", "blind", "deaf", "impairment",
    },
    "senior citizen": {
        "senior", "elderly", "old age", "pension", "vridha", "old-age",
        "geriatric", "retirement",
    },
    "business": {
        "business", "enterprise", "startup", "msme", "loan", "entrepreneur",
        "mudra", "standup", "self-employment", "udyog",
    },
    "social security": {
        "social security", "pension", "insurance", "welfare", "safety net",
        "social protection", "bima",
    },
}


def _detect_state_from_text(text: str) -> set[str]:
    """Detect Indian state names mentioned in text."""
    text_lower = text.lower()
    detected: set[str] = set()
    for state in INDIAN_STATES:
        if state in text_lower:
            detected.add(state)
    return detected


def _detect_state_from_url(url: str) -> str | None:
    """Detect state from URL domain."""
    url_lower = url.lower()
    for domain_part, state in STATE_DOMAIN_HINTS.items():
        if domain_part in url_lower:
            return state
    return None


def _is_central_or_national(text: str, url: str) -> bool:
    """Check if a result is about a Central Government / national scheme."""
    text_lower = text.lower()
    url_lower = url.lower()
    central_indicators = {
        "central government", "government of india", "union government",
        "ministry of", "national scheme", "pradhan mantri", "pm ", "pm-",
        "all india", "pan india", "nationwide", "across india",
        "myscheme.gov.in", "india.gov.in", "nsp.gov.in",
        "scholarships.gov.in", "services.india.gov.in",
    }
    return any(indicator in text_lower or indicator in url_lower for indicator in central_indicators)


def _need_keywords_for(goal: str) -> set[str]:
    """Return the keyword set for a given need/goal."""
    goal_lower = goal.lower().strip()
    for key, keywords in NEED_FILTER_KEYWORDS.items():
        if key in goal_lower or goal_lower in key:
            return keywords
    return set()


@dataclass
class RetrievalDiagnostics:
    """Diagnostic information for debugging retrieval quality (never contains secrets)."""
    state: str = ""
    need: str = ""
    generated_queries: list[str] = field(default_factory=list)
    tavily_results: list[dict[str, Any]] = field(default_factory=list)
    rejection_reasons: list[dict[str, str]] = field(default_factory=list)
    final_recommendations: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "need": self.need,
            "generated_queries": list(self.generated_queries),
            "tavily_result_count": len(self.tavily_results),
            "tavily_results": self.tavily_results,
            "rejection_reasons": self.rejection_reasons,
            "final_recommendation_count": len(self.final_recommendations),
        }


@dataclass
class SearchHit:
    title: str
    url: str
    content: str
    score: float = 0.0
    official: bool = False
    detected_state: str | None = None
    is_central: bool = False
    need_match: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "official": self.official,
            "source_verification": source_verification(self.url),
        }


@dataclass
class RetrievalPack:
    queries: list[str]
    hits: list[SearchHit]
    schemes: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    diagnostics: RetrievalDiagnostics | None = None

    def metadata(self) -> dict[str, Any]:
        meta = {
            "mode": "live_web_search",
            "provider": "tavily",
            "cached": False,
            "queries": list(self.queries),
            "result_count": len(self.hits),
            "official_result_count": sum(1 for hit in self.hits if hit.official),
            "source_urls": [hit.url for hit in self.hits],
        }
        if self.diagnostics:
            meta["diagnostics"] = self.diagnostics.as_dict()
        return meta


def _hit_from_tavily(item: dict[str, Any]) -> SearchHit | None:
    url = normalize_url(str(item.get("url") or ""))
    if not url:
        return None
    title = str(item.get("title") or "").strip()
    content = str(item.get("content") or item.get("raw_content") or "").strip()
    score = float(item.get("score") or 0.0)
    return SearchHit(
        title=title,
        url=url,
        content=content,
        score=score,
        official=is_official_government_url(url),
    )


def _annotate_hit(hit: SearchHit, profile_state: str, profile_need: str) -> None:
    """Annotate a search hit with state detection and need-match info."""
    combined_text = f"{hit.title} {hit.content}"

    # Detect state from URL domain first, then from text
    url_state = _detect_state_from_url(hit.url)
    text_states = _detect_state_from_text(combined_text)

    if url_state:
        hit.detected_state = url_state
    elif text_states:
        hit.detected_state = next(iter(text_states))
    else:
        hit.detected_state = None

    hit.is_central = _is_central_or_national(combined_text, hit.url)

    # Need matching
    if profile_need:
        need_kw = _need_keywords_for(profile_need)
        if need_kw:
            combined_lower = combined_text.lower()
            hit.need_match = any(kw in combined_lower for kw in need_kw)
        else:
            hit.need_match = True  # Unknown need, don't filter
    else:
        hit.need_match = True


def check_state_relevance(
    hit: SearchHit, profile_state: str
) -> tuple[bool, str]:
    """Check if a search hit is relevant for the requested state.

    Returns (is_relevant, reason).
    """
    if not profile_state:
        return True, "no_state_requested"

    profile_state_lower = profile_state.lower().strip()

    # Central/national schemes are always relevant
    if hit.is_central:
        return True, "central_scheme"

    # Exact state match
    if hit.detected_state and hit.detected_state == profile_state_lower:
        return True, "exact_state_match"

    # Hit belongs exclusively to a DIFFERENT state → reject
    if hit.detected_state and hit.detected_state != profile_state_lower:
        return False, f"wrong_state:{hit.detected_state}"

    # No state detected — could be relevant (generic result)
    # Check if profile state appears in the text
    combined = f"{hit.title} {hit.content}".lower()
    if profile_state_lower in combined:
        return True, "state_in_text"

    # No state info → keep but mark as uncertain
    return True, "no_state_detected"


def check_need_relevance(
    hit: SearchHit, profile_need: str
) -> tuple[bool, str]:
    """Check if a search hit matches the requested need/goal.

    Returns (is_relevant, reason).
    """
    if not profile_need:
        return True, "no_need_specified"

    if hit.need_match:
        return True, "need_match"

    return False, f"wrong_need:no_{profile_need.lower()}_keywords"


def rank_hits(
    hits: list[SearchHit],
    profile_state: str = "",
    profile_need: str = "",
) -> list[SearchHit]:
    """Rank and filter hits by relevance, prioritizing state + need + official."""
    unique: dict[str, SearchHit] = {}
    for hit in hits:
        key = normalize_url(hit.url).lower()
        if key not in unique:
            unique[key] = hit
    ranked = list(unique.values())

    def sort_key(hit: SearchHit) -> tuple:
        profile_state_lower = profile_state.lower().strip() if profile_state else ""
        # Higher priority (lower sort key) for:
        #   1. State match (exact > central > no-state > wrong-state)
        #   2. Need match
        #   3. Official source
        #   4. Higher Tavily score

        state_rank = 3  # default: unknown
        if hit.detected_state:
            if hit.detected_state == profile_state_lower:
                state_rank = 0  # exact match
            elif hit.is_central:
                state_rank = 1  # central/national
            else:
                state_rank = 4  # wrong state
        elif hit.is_central:
            state_rank = 1
        elif profile_state_lower and profile_state_lower in f"{hit.title} {hit.content}".lower():
            state_rank = 2  # state mentioned in text

        need_rank = 0 if hit.need_match else 1
        official_rank = 0 if hit.official else 1
        score_rank = -hit.score

        return (state_rank, need_rank, official_rank, score_rank, hit.url)

    ranked.sort(key=sort_key)
    return ranked


class LiveSchemeRetriever:
    """Search the public web at request time via Tavily."""

    def __init__(
        self,
        *,
        tavily_client: Any | None = None,
        search_fn: Any | None = None,
        extract_fn: Any | None = None,
        max_results_per_query: int = 8,
        max_queries: int = 10,
    ) -> None:
        self._tavily_client = tavily_client
        self._search_fn = search_fn
        self._extract_fn = extract_fn
        self.max_results_per_query = max_results_per_query
        self.max_queries = max_queries

    def _client(self) -> Any:
        if self._tavily_client is not None:
            return self._tavily_client
        try:
            from tavily import TavilyClient
            from agent.secrets import get_tavily_api_key
        except Exception as exc:
            raise LiveSearchError(f"Live search client is unavailable: {exc}") from exc
        try:
            self._tavily_client = TavilyClient(api_key=get_tavily_api_key())
        except Exception as exc:
            raise LiveSearchError(str(exc)) from exc
        return self._tavily_client

    def search(self, query: str, *, prefer_official: bool = True) -> list[SearchHit]:
        if self._search_fn is not None:
            raw = self._search_fn(query, prefer_official=prefer_official)
            if isinstance(raw, list) and raw and isinstance(raw[0], SearchHit):
                return raw
            hits = [_hit_from_tavily(item) for item in (raw or []) if isinstance(item, dict)]
            return [hit for hit in hits if hit is not None]

        client = self._client()
        kwargs: dict[str, Any] = {
            "query": query,
            "max_results": self.max_results_per_query,
            "include_answer": False,
            "search_depth": "basic",
            "timeout": get_tavily_timeout_seconds(),
        }
        from agent import retry

        try:
            try:
                payload = retry.with_retries(lambda: client.search(**kwargs), provider="tavily", operation="search")
            except TypeError:
                # Tavily SDK build without a `timeout` kwarg: retry without it.
                kwargs.pop("timeout", None)
                payload = retry.with_retries(lambda: client.search(**kwargs), provider="tavily", operation="search")
        except Exception as exc:
            raise LiveSearchError(f"Live search failed: {exc}") from exc

        results = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(results, list):
            raise LiveSearchError("Live search returned an unexpected response.")
        hits = [_hit_from_tavily(item) for item in results if isinstance(item, dict)]
        return [hit for hit in hits if hit is not None]

    def retrieve_pack(
        self,
        profile: dict[str, Any] | str,
        *,
        top_k: int = 8,
        query: str | None = None,
        client: Any | None = None,
        include_llm_queries: bool = True,
    ) -> RetrievalPack:
        from agent.query_builder import build_search_queries

        if isinstance(profile, str):
            queries = [profile]
            profile_dict: dict[str, Any] = {"other_relevant_information": profile}
        else:
            profile_dict = profile
            queries = build_search_queries(
                profile_dict, client=client, include_llm=include_llm_queries
            )
        if query:
            queries = [query, *[item for item in queries if item != query]]

        profile_state = str(profile_dict.get("state") or "").strip()
        profile_need = str(
            profile_dict.get("goal")
            or profile_dict.get("need")
            or profile_dict.get("current_situation")
            or ""
        ).strip()

        # Diagnostics (safe: no secrets, no sensitive PII)
        diag = RetrievalDiagnostics(
            state=profile_state,
            need=profile_need,
            generated_queries=list(queries[:self.max_queries]),
        )

        logger.info(
            "RETRIEVAL DIAGNOSTICS | STATE: %s | NEED: %s | QUERIES: %s",
            profile_state, profile_need,
            queries[:self.max_queries],
        )

        hits: list[SearchHit] = []
        used_queries: list[str] = []
        last_error: Exception | None = None
        for item in queries[: self.max_queries]:
            used_queries.append(item)
            try:
                batch = self.search(item, prefer_official=True)
                hits.extend(batch)
            except LiveSearchError as exc:
                last_error = exc
                continue

        # Annotate hits with state/need detection
        for hit in hits:
            _annotate_hit(hit, profile_state, profile_need)

        # Log raw Tavily results for diagnostics
        for hit in hits:
            diag.tavily_results.append({
                "title": hit.title,
                "url": hit.url,
                "domain": hit.url.split("/")[2] if len(hit.url.split("/")) > 2 else "",
                "detected_state": hit.detected_state,
                "is_central": hit.is_central,
                "need_match": hit.need_match,
                "official": hit.official,
                "score": hit.score,
            })

        # Filter by state and need relevance
        filtered_hits: list[SearchHit] = []
        for hit in hits:
            state_ok, state_reason = check_state_relevance(hit, profile_state)
            need_ok, need_reason = check_need_relevance(hit, profile_need)

            if not state_ok:
                diag.rejection_reasons.append({
                    "title": hit.title,
                    "url": hit.url,
                    "reason": f"wrong_state ({state_reason})",
                })
                logger.info(
                    "REJECTED | %s | state_reason=%s | url=%s",
                    hit.title, state_reason, hit.url,
                )
                continue

            if not need_ok:
                diag.rejection_reasons.append({
                    "title": hit.title,
                    "url": hit.url,
                    "reason": f"wrong_need ({need_reason})",
                })
                logger.info(
                    "REJECTED | %s | need_reason=%s | url=%s",
                    hit.title, need_reason, hit.url,
                )
                continue

            filtered_hits.append(hit)

        # Rank filtered hits
        ranked = rank_hits(filtered_hits, profile_state, profile_need)

        if not ranked:
            if last_error:
                raise LiveSearchError(
                    "Live search failed and no current government scheme pages were retrieved. "
                    f"{last_error}"
                )
            return RetrievalPack(
                queries=used_queries, hits=[], schemes=[],
                diagnostics=diag,
            )

        extract = self._extract_fn
        if extract is None:
            from agent.scheme_extractor import extract_schemes_from_hits

            extract = extract_schemes_from_hits
        schemes = extract(ranked, profile_dict, client=client)
        grounded = _drop_ungrounded_schemes(schemes, ranked)

        # Post-filter extracted schemes for state and need relevance
        validated = _validate_scheme_relevance(grounded, profile_state, profile_need, diag)

        for scheme in validated:
            diag.final_recommendations.append({
                "scheme_name": scheme.get("scheme_name", ""),
                "source": scheme.get("official_source_url", ""),
                "state_applicability": scheme.get("_state_applicability", "unknown"),
            })

        logger.info(
            "RETRIEVAL COMPLETE | state=%s | need=%s | "
            "raw_hits=%d | filtered_hits=%d | schemes=%d | final=%d",
            profile_state, profile_need,
            len(hits), len(ranked), len(grounded), len(validated),
        )

        return RetrievalPack(
            queries=used_queries, hits=ranked,
            schemes=validated[:top_k],
            diagnostics=diag,
        )

    def retrieve_schemes(
        self,
        profile: dict[str, Any] | str,
        top_k: int = 8,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        pack = self.retrieve_pack(profile, top_k=top_k, **kwargs)
        return pack.schemes


def _validate_scheme_relevance(
    schemes: list[dict[str, Any]],
    profile_state: str,
    profile_need: str,
    diag: RetrievalDiagnostics,
) -> list[dict[str, Any]]:
    """Deterministic post-extraction filter: reject schemes whose text
    indicates they belong exclusively to a different state or an unrelated need.
    """
    if not profile_state and not profile_need:
        return schemes

    profile_state_lower = profile_state.lower().strip() if profile_state else ""
    validated: list[dict[str, Any]] = []

    for scheme in schemes:
        blob = " ".join(
            str(scheme.get(f) or "")
            for f in ("scheme_name", "description", "eligibility", "benefits",
                      "official_source_url", "government_department")
        ).lower()

        # ── State relevance check ──
        if profile_state_lower:
            mentioned_states = _detect_state_from_text(blob)
            url_state = _detect_state_from_url(str(scheme.get("official_source_url") or ""))
            if url_state:
                mentioned_states.add(url_state)

            is_central = _is_central_or_national(blob, str(scheme.get("official_source_url") or ""))

            if mentioned_states and profile_state_lower not in mentioned_states and not is_central:
                diag.rejection_reasons.append({
                    "title": scheme.get("scheme_name", ""),
                    "url": scheme.get("official_source_url", ""),
                    "reason": f"wrong_state_in_scheme (detected: {mentioned_states})",
                })
                logger.info(
                    "SCHEME REJECTED (state) | %s | detected_states=%s | needed=%s",
                    scheme.get("scheme_name"), mentioned_states, profile_state_lower,
                )
                continue

            # Annotate state applicability
            scheme = dict(scheme)
            if profile_state_lower in mentioned_states:
                scheme["_state_applicability"] = "exact_match"
            elif is_central:
                scheme["_state_applicability"] = "central_scheme"
            else:
                scheme["_state_applicability"] = "unconfirmed"

        # ── Need relevance check ──
        if profile_need:
            need_kw = _need_keywords_for(profile_need)
            if need_kw:
                has_need_match = any(kw in blob for kw in need_kw)
                if not has_need_match:
                    diag.rejection_reasons.append({
                        "title": scheme.get("scheme_name", ""),
                        "url": scheme.get("official_source_url", ""),
                        "reason": f"wrong_need (no {profile_need} keywords in scheme)",
                    })
                    logger.info(
                        "SCHEME REJECTED (need) | %s | needed=%s",
                        scheme.get("scheme_name"), profile_need,
                    )
                    continue

        validated.append(scheme)

    return validated


def _drop_ungrounded_schemes(
    schemes: list[dict[str, Any]], hits: list[SearchHit]
) -> list[dict[str, Any]]:
    allowed = {normalize_url(hit.url).lower() for hit in hits}
    grounded: list[dict[str, Any]] = []
    for scheme in schemes:
        source = normalize_url(
            str(
                scheme.get("official_source_url")
                or scheme.get("official_source")
                or scheme.get("source_url")
                or ""
            )
        )
        apply_url = normalize_url(str(scheme.get("application_url") or scheme.get("apply_url") or ""))
        source_ok = source.lower() in allowed
        apply_ok = apply_url.lower() in allowed if apply_url else True
        if not source or not source_ok:
            continue
        if apply_url and not apply_ok and not is_official_government_url(apply_url):
            scheme = dict(scheme)
            scheme["application_url"] = source
            scheme["missing_information"] = list(scheme.get("missing_information") or [])
            scheme["missing_information"].append(
                "Application URL was omitted because it was not present in live search results."
            )
        scheme = dict(scheme)
        scheme["official_source_url"] = source
        scheme["official_source"] = source
        scheme["source_verification"] = source_verification(source)
        if not scheme.get("application_url"):
            scheme["application_url"] = source
        grounded.append(scheme)
    official = [item for item in grounded if item.get("source_verification", {}).get("is_official_government_source")]
    supporting = [item for item in grounded if item not in official]
    return official + supporting
