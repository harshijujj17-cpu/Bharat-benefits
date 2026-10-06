"""Live production-pipeline QA for Government Scheme Navigator.

This harness sends real HTTP requests to a running FastAPI server. It never mocks,
patches, or substitutes Tavily, Gemini, retrieval results, or scheme data.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

LOCATIONS = [
    "Telangana", "Kerala", "Madhya Pradesh", "Maharashtra",
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands",
    "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Lakshadweep", "Puducherry",
]
UNION_TERRITORIES = set(LOCATIONS[-8:])

# These profiles cover the requested matrix. Status fields use API values, not
# inferred booleans, so unknown and negative states remain distinguishable.
PROFILE_MATRIX = {
    "T01": dict(age=16, gender="Female", education="School student", occupation="student", category="OBC", annual_income=120000, disability_status="No", farmer_status="No", student_status="Yes", employment_status="Student", goal="Education; scholarship support"),
    "T02": dict(age=21, gender="Female", education="B.Tech", occupation="student", category="OBC", annual_income=250000, disability_status="No", farmer_status="No", student_status="Yes", employment_status="Student", goal="Education; scholarship support"),
    "T03": dict(age=30, gender="Female", education=None, occupation="homemaker", category="SC", annual_income=150000, disability_status="No", farmer_status="No", student_status="No", employment_status="Homemaker", goal="Women support; financial assistance"),
    "T04": dict(age=35, gender="Male", education=None, occupation="farmer", category="OBC", annual_income=150000, disability_status="No", farmer_status="Yes", student_status="No", employment_status="Self-employed", goal="Agriculture support"),
    "T05": dict(age=45, gender="Female", education=None, occupation="farmer", category="SC", annual_income=200000, disability_status="No", farmer_status="Yes", student_status="No", employment_status="Self-employed", goal="Agriculture support; women support"),
    "T06": dict(age=32, gender="Male", education=None, occupation="self-employed", category="SC", annual_income=180000, disability_status="Yes", farmer_status="No", student_status="No", employment_status="Self-employed", goal="Disability support; start a business"),
    "T07": dict(age=60, gender="Female", education=None, occupation="retired", category="General", annual_income=150000, disability_status="No", farmer_status="No", student_status="No", employment_status="Retired", goal="Pension / retirement; healthcare"),
    "T08": dict(age=70, gender="Male", education=None, occupation="retired", category="OBC", annual_income=100000, disability_status="No", farmer_status="No", student_status="No", employment_status="Retired", goal="Pension / retirement; healthcare"),
    "T09": dict(age=28, gender="Female", education=None, occupation="small business owner", category="OBC", annual_income=300000, disability_status="No", farmer_status="No", student_status="No", employment_status="Self-employed", goal="Start a business; financial assistance"),
    "T10": dict(age=40, gender="Male", education=None, occupation="farmer", category="SC", annual_income=80000, disability_status="No", farmer_status="Yes", student_status="No", employment_status="Self-employed", goal="Agriculture support"),
    "T11": dict(age=25, gender="Female", education=None, occupation="unemployed", category="SC", annual_income=100000, disability_status="Yes", farmer_status="No", student_status="No", employment_status="Unemployed", goal="Find employment; disability support"),
    "T12": dict(age=50, gender="Male", education=None, occupation="farmer", category="General", annual_income=120000, disability_status="No", farmer_status="Yes", student_status="No", employment_status="Self-employed", goal="Agriculture support"),
}

# Additional edge coverage. The regular matrix already covers ages 25/40/60/70,
# categories SC/OBC/General, each occupation/status, and gender combinations.
EDGE_CASES = {
    "E01": dict(age=5, gender="Female", education="Primary school", occupation="student", category="General", annual_income=0, disability_status="No", farmer_status="No", student_status="Yes", employment_status="Student", goal="Child welfare; education"),
    "E02": dict(age=18, gender="Male", education="12th pass", occupation="student", category="ST", annual_income=0, disability_status="No", farmer_status="No", student_status="Yes", employment_status="Student", goal="Education; skill development"),
    "E03": dict(age=40, gender="Female", education=None, occupation="self-employed", category="General", annual_income=5000000, disability_status="No", farmer_status="No", student_status="No", employment_status="Self-employed", goal="Start a business"),
}


def canonical_url(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def domain(value: str | None) -> str:
    return urlparse(value or "").netloc.lower().removeprefix("www.")


def is_government_domain(value: str | None) -> bool:
    host = domain(value)
    return host.endswith(".gov.in") or host.endswith(".nic.in") or host == "myscheme.gov.in"


def government_scope(scheme: dict[str, Any], location: str) -> str:
    department = str(scheme.get("government_department") or "").lower()
    text = " ".join(str(scheme.get(key) or "") for key in ("scheme_name", "description", "eligibility", "government_department")).lower()
    if "government of india" in department or "ministry" in department or "central" in department:
        return "CENTRAL"
    if location.lower() in text:
        return "UT" if location in UNION_TERRITORIES else "STATE"
    return "UNKNOWN"


def eligibility_class(scheme: dict[str, Any]) -> str:
    status = str(scheme.get("eligibility_status") or "").lower()
    missing = scheme.get("missing_information") or []
    if status in {"likely_not_eligible", "not_relevant", "ineligible"}:
        return "NOT_A_MATCH"
    if status in {"relevant", "eligible"} and not missing:
        return "STRONG_MATCH"
    if status in {"relevant", "eligible", "possibly_eligible"}:
        return "POSSIBLE_MATCH"
    return "NEEDS_VERIFICATION"


def make_payload(location: str, profile: dict[str, Any]) -> dict[str, Any]:
    income = profile["annual_income"]
    return {
        **profile,
        "state": location,
        "annual_household_income_inr": income,
        "district": None,
        "current_situation": profile["occupation"],
        "other_relevant_information": None,
        "top_k": 8,
    }


def request_json(
    url: str, payload: dict[str, Any] | None, timeout: float, method: str = "POST"
) -> tuple[int, Any, float, str | None]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - explicit QA endpoint
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw), time.monotonic() - started, None
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw[:500]}
        return exc.code, parsed, time.monotonic() - started, None
    except (URLError, TimeoutError, OSError) as exc:
        return 0, None, time.monotonic() - started, f"{type(exc).__name__}: {exc}"


def validate_response(location: str, payload: dict[str, Any], status: int, response: Any) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    warnings: list[str] = []
    schemes: list[dict[str, Any]] = []
    if status != 200 or not isinstance(response, dict):
        return [f"http_{status}"], warnings, schemes

    retrieval = response.get("retrieval") or {}
    if retrieval.get("mode") != "live_web_search" or retrieval.get("provider") != "tavily":
        failures.append("missing_live_tavily_retrieval_metadata")
    if retrieval.get("cached") is not False:
        failures.append("live_retrieval_not_explicitly_uncached")
    queries = retrieval.get("queries") or []
    if not queries:
        failures.append("no_generated_queries_returned")
    elif not any(location.lower() in str(query).lower() for query in queries):
        failures.append("no_state_specific_generated_query")
    source_urls = {canonical_url(url) for url in retrieval.get("source_urls") or []}

    for scheme in response.get("recommendations") or []:
        source_url = scheme.get("official_source_url") or scheme.get("official_source")
        verification = scheme.get("source_verification") or {}
        scheme_issues: list[str] = []
        if not scheme.get("scheme_name"):
            scheme_issues.append("missing_scheme_name")
        if not source_url:
            scheme_issues.append("missing_official_source_url")
        elif canonical_url(source_url) not in source_urls:
            scheme_issues.append("source_url_not_grounded_in_tavily_results")
        if source_url and not (verification.get("is_official_government_source") or is_government_domain(source_url)):
            scheme_issues.append("unverified_non_government_source")
        if not scheme.get("relevance_explanation"):
            scheme_issues.append("missing_gemini_relevance_explanation")
        if not scheme.get("eligibility_status"):
            scheme_issues.append("missing_gemini_eligibility_status")
        if scheme.get("eligibility_status") in {"relevant", "eligible"} and not scheme.get("eligibility"):
            scheme_issues.append("eligibility_claim_without_evidence")
        if scheme.get("eligibility_status") in {"relevant", "eligible"} and not scheme.get("missing_information"):
            warnings.append("eligibility_has_no_explicit_missing_information")
        if scheme.get("eligibility_status") in {"cannot_confirm", "unknown", None} and not scheme.get("missing_information"):
            scheme_issues.append("unknown_eligibility_without_missing_information")

        scope = government_scope(scheme, location)
        text = " ".join(str(scheme.get(k) or "") for k in ("scheme_name", "description", "government_department")).lower()
        other_locations = [name for name in LOCATIONS if name != location and name.lower() in text]
        if scope == "UNKNOWN" and other_locations:
            scheme_issues.append(f"possible_wrong_state_attribution:{other_locations[0]}")
        for issue in scheme_issues:
            (failures if issue not in {"unverified_non_government_source"} else warnings).append(issue)
        schemes.append({
            "name": scheme.get("scheme_name"),
            "url": source_url,
            "domain": domain(source_url),
            "scope": scope,
            "official": bool(verification.get("is_official_government_source") or is_government_domain(source_url)),
            "eligibility_class": eligibility_class(scheme),
            "eligibility_status": scheme.get("eligibility_status"),
            "missing_information": scheme.get("missing_information") or [],
            "benefits": scheme.get("benefits"),
            "required_documents": scheme.get("required_documents") or [],
            "application_process": scheme.get("application_process"),
            "verification": verification,
            "issues": scheme_issues,
        })
    return failures, warnings, schemes


def validate_response_profile(payload: dict[str, Any], response: Any) -> list[str]:
    """Ensure the returned journey remains tied to the submitted profile."""
    if not isinstance(response, dict):
        return []
    journey = response.get("journey")
    # Only judge profile preservation when a real journey profile exists.
    # A 502/503 provider-failure body has no journey — skip (no false cascade).
    if not isinstance(journey, dict) or "profile" not in journey:
        return []
    profile = journey.get("profile") or {}
    expected = {
        "age": payload.get("age"),
        "state": payload.get("state"),
        "gender": payload.get("gender"),
        "category": payload.get("category"),
        "occupation": payload.get("occupation"),
        "annual_household_income_inr": payload.get("annual_household_income_inr"),
        "disability_status": payload.get("disability_status"),
        "farmer_status": payload.get("farmer_status"),
        "student_status": payload.get("student_status"),
    }
    return [
        f"returned_profile_mismatch:{key}"
        for key, value in expected.items()
        if profile.get(key) != value
    ]


def write_reports(rows: list[dict[str, Any]], output_dir: Path, started_at: str, health: dict[str, Any] | None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "live_qa_results.json").write_text(json.dumps({"started_at": started_at, "health": health, "rows": rows}, indent=2), encoding="utf-8")
    fields = ["location", "location_type", "profile", "status", "schemes", "official_sources", "eligibility_issues", "latency_seconds", "outcome", "failures", "warnings"]
    with (output_dir / "live_qa_table.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "location": row["location"], "location_type": row["location_type"], "profile": row["profile"],
                "status": row["http_status"], "schemes": row["scheme_count"], "official_sources": row["official_source_count"],
                "eligibility_issues": "; ".join(row["eligibility_issues"]), "latency_seconds": f"{row['latency_seconds']:.2f}",
                "outcome": row["outcome"], "failures": "; ".join(row["failures"]), "warnings": "; ".join(row["warnings"]),
            })

    outcomes = Counter(row["outcome"] for row in rows)
    failures = [row for row in rows if row["failures"]]
    warnings = [row for row in rows if row["warnings"]]
    slow = [row for row in rows if row["latency_seconds"] >= 30]
    report = [
        "# Live Backend QA Summary", "",
        f"- Total tests: {len(rows)}", f"- Passed: {outcomes['PASS']}", f"- Failed: {outcomes['FAIL']}",
        f"- Warnings: {len(warnings)}", f"- No relevant schemes found: {outcomes['NO_RELEVANT_SCHEMES_FOUND']}",
        f"- Needs verification: {sum(item['eligibility_counts'].get('NEEDS_VERIFICATION', 0) for item in rows)}",
        f"- Slow API calls (>=30s): {len(slow)}", "",
        "## Failed cases", *([f"- {r['location']} {r['profile']}: {', '.join(r['failures'])}" for r in failures] or ["- None"]),
        "", "## Warnings", *([f"- {r['location']} {r['profile']}: {', '.join(r['warnings'])}" for r in warnings] or ["- None"]),
        "", "## Slow API calls", *([f"- {r['location']} {r['profile']}: {r['latency_seconds']:.2f}s" for r in slow] or ["- None"]),
    ]
    (output_dir / "live_qa_summary.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--include-edges", action="store_true", help="Run edge profiles for every location.")
    parser.add_argument("--locations", nargs="*", choices=LOCATIONS)
    parser.add_argument("--output-dir", default="qa/results")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    locations = args.locations or LOCATIONS
    profiles = dict(PROFILE_MATRIX)
    if args.include_edges:
        profiles.update(EDGE_CASES)
    started_at = datetime.now(UTC).isoformat()
    _, health, _, health_error = request_json(f"{base_url}/health", None, args.timeout, method="GET")
    if health_error:
        print(f"Health check failed: {health_error}")
        return 2
    if not isinstance(health, dict) or health.get("status") != "ok":
        print("Health check is not OK; do not run paid live QA against degraded providers.")
        return 2
    if health.get("retrieval") != "live_web_search" or health.get("provider") != "tavily" or health.get("stores_schemes") is not False:
        print("Health metadata does not prove the required live-only Tavily configuration.")
        return 2

    rows: list[dict[str, Any]] = []
    previous_by_location: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {}
    total = len(locations) * len(profiles)

    # Resume: reload any previously persisted rows and skip completed cases.
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "live_qa_results.json"
    progress_path = output_dir / "progress.json"
    done: set[tuple[str, str]] = set()
    if results_path.exists():
        try:
            existing = json.loads(results_path.read_text(encoding="utf-8"))
            rows = list(existing.get("rows", []))
            done = {(r["location"], r["profile"]) for r in rows}
            print(f"Resuming: {len(rows)} persisted rows found; continuing.", flush=True)
        except Exception:
            rows = []
            done = set()

    def persist(completed_location: str, completed_profile: str) -> None:
        payload_json = json.dumps({"started_at": started_at, "health": health, "rows": rows}, ensure_ascii=False, indent=1)
        tmp = results_path.with_suffix(".tmp")
        tmp.write_text(payload_json, encoding="utf-8")
        os.replace(tmp, results_path)
        progress_path.write_text(json.dumps({
            "completed": len(rows),
            "total": total,
            "last_location": completed_location,
            "last_profile": completed_profile,
            "timestamp": datetime.now(UTC).isoformat(),
        }, indent=1), encoding="utf-8")

    for position, location in enumerate(locations, start=1):
        for profile_id, profile in profiles.items():
            if (location, profile_id) in done:
                continue
            payload = make_payload(location, profile)
            status, response, latency, network_error = request_json(f"{base_url}/recommend", payload, args.timeout)
            failures, warnings, schemes = validate_response(location, payload, status, response)
            failures.extend(validate_response_profile(payload, response))
            if network_error:
                failures.append(f"network_error:{network_error}")
            names = tuple(item["name"] or "" for item in schemes)
            queries = tuple((response.get("retrieval") or {}).get("queries") or []) if isinstance(response, dict) else ()
            previous = previous_by_location.get(location)
            if previous and previous[1] == names and previous[2] == queries and names:
                warnings.append(f"possible_stale_duplicate_of:{previous[0]}")
            previous_by_location[location] = (profile_id, names, queries)
            eligibility_counts = Counter(item["eligibility_class"] for item in schemes)
            eligibility_issues = [issue for item in schemes for issue in item["issues"] if "eligibility" in issue or "attribution" in issue]
            outcome = "FAIL" if failures else ("NO_RELEVANT_SCHEMES_FOUND" if not schemes else "PASS")
            row = {
                "location": location,
                "location_type": "UT" if location in UNION_TERRITORIES else "STATE",
                "profile": profile_id,
                "payload": payload,
                "http_status": status,
                "latency_seconds": round(latency, 3),
                "outcome": outcome,
                "scheme_count": len(schemes),
                "official_source_count": sum(item["official"] for item in schemes),
                "generated_queries": list(queries),
                "retrieval": response.get("retrieval") if isinstance(response, dict) else None,
                "schemes": schemes,
                "eligibility_counts": dict(eligibility_counts),
                "eligibility_issues": eligibility_issues,
                "failures": sorted(set(failures)),
                "warnings": sorted(set(warnings)),
                "network_error": network_error,
                "provider_error": ((response.get("detail") or {}).get("error") if isinstance(response, dict) else None),
            }
            rows.append(row)
            persist(location, profile_id)
            done.add((location, profile_id))
            print(f"[{len(rows)}/{total}] {location} {profile_id}: {outcome}; {len(schemes)} schemes; {latency:.1f}s", flush=True)
            # Do not bypass production rate limiting. Back off only when server requests it.
            if status == 429:
                time.sleep(65)

    write_reports(rows, Path(args.output_dir), started_at, health)
    failed = sum(row["outcome"] == "FAIL" for row in rows)
    print(f"Complete: {len(rows)} tests, {failed} failures. Reports: {args.output_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
