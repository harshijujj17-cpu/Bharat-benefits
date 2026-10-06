"""Request-time live web retrieval for government schemes.

Nothing retrieved here is written to disk. Results exist only in memory
for the current request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.model_config import get_tavily_timeout_seconds
from rag.official_sources import is_official_government_url, normalize_url, source_verification


class LiveSearchError(RuntimeError):
    """Raised when the live search provider cannot be reached or returns an error."""


@dataclass
class SearchHit:
    title: str
    url: str
    content: str
    score: float = 0.0
    official: bool = False

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

    def metadata(self) -> dict[str, Any]:
        return {
            "mode": "live_web_search",
            "provider": "tavily",
            "cached": False,
            "queries": list(self.queries),
            "result_count": len(self.hits),
            "official_result_count": sum(1 for hit in self.hits if hit.official),
            "source_urls": [hit.url for hit in self.hits],
        }


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


def rank_hits(hits: list[SearchHit]) -> list[SearchHit]:
    unique: dict[str, SearchHit] = {}
    for hit in hits:
        key = normalize_url(hit.url).lower()
        if key not in unique:
            unique[key] = hit
    ranked = list(unique.values())
    ranked.sort(key=lambda hit: (not hit.official, -hit.score, hit.url))
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
        max_queries: int = 3,
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
                return rank_hits(raw)
            hits = [_hit_from_tavily(item) for item in (raw or []) if isinstance(item, dict)]
            return rank_hits([hit for hit in hits if hit is not None])

        client = self._client()
        kwargs: dict[str, Any] = {
            "query": query,
            "max_results": self.max_results_per_query,
            "include_answer": False,
            "search_depth": "basic",
            "timeout": get_tavily_timeout_seconds(),
        }
        try:
            payload = client.search(**kwargs)
        except TypeError:
            # Tavily SDK build without a `timeout` kwarg: retry without it.
            kwargs.pop("timeout", None)
            try:
                payload = client.search(**kwargs)
            except Exception as exc:
                raise LiveSearchError(f"Live search failed: {exc}") from exc
        except Exception as exc:
            raise LiveSearchError(f"Live search failed: {exc}") from exc

        results = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(results, list):
            raise LiveSearchError("Live search returned an unexpected response.")
        hits = [_hit_from_tavily(item) for item in results if isinstance(item, dict)]
        ranked = rank_hits([hit for hit in hits if hit is not None])
        if prefer_official:
            official = [hit for hit in ranked if hit.official]
            supporting = [hit for hit in ranked if not hit.official]
            return official + supporting
        return ranked

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

        hits: list[SearchHit] = []
        used_queries: list[str] = []
        last_error: Exception | None = None
        for item in queries[: self.max_queries]:
            used_queries.append(item)
            try:
                hits.extend(self.search(item, prefer_official=True))
            except LiveSearchError as exc:
                last_error = exc
                continue

        hits = rank_hits(hits)
        if not hits:
            if last_error:
                raise LiveSearchError(
                    "Live search failed and no current government scheme pages were retrieved. "
                    f"{last_error}"
                )
            return RetrievalPack(queries=used_queries, hits=[], schemes=[])

        extract = self._extract_fn
        if extract is None:
            from agent.scheme_extractor import extract_schemes_from_hits

            extract = extract_schemes_from_hits
        schemes = extract(hits, profile_dict, client=client)
        grounded = _drop_ungrounded_schemes(schemes, hits)
        return RetrievalPack(queries=used_queries, hits=hits, schemes=grounded[:top_k])

    def retrieve_schemes(
        self,
        profile: dict[str, Any] | str,
        top_k: int = 8,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        pack = self.retrieve_pack(profile, top_k=top_k, **kwargs)
        return pack.schemes


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
