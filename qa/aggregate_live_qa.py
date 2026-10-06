"""Combine live backend and frontend QA batch artifacts into final reports."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path("qa/full-results")
OUTPUT = ROOT / "combined"


def load_backend_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(ROOT.glob("backend-*/live_qa_results.json")):
        rows.extend(json.loads(path.read_text(encoding="utf-8")).get("rows", []))
    return rows


def load_frontend_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(ROOT.glob("frontend-*/frontend_qa_results.json")):
        rows.extend(json.loads(path.read_text(encoding="utf-8")))
    return rows


def main() -> None:
    backend = load_backend_rows()
    frontend = load_frontend_rows()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    backend_outcomes = Counter(row.get("outcome") for row in backend)
    frontend_outcomes = Counter(row.get("status") for row in frontend)
    backend_failures = [row for row in backend if row.get("failures")]
    frontend_failures = [row for row in frontend if row.get("failures")]
    warnings = [row for row in backend if row.get("warnings")] + [row for row in frontend if row.get("warnings")]
    retrieval_failures = [row for row in backend if any("retrieval" in issue or "grounded" in issue or "source" in issue for issue in row.get("failures", []))]
    eligibility_failures = [row for row in backend if row.get("eligibility_issues")]
    slow = [row for row in backend if row.get("latency_seconds", 0) >= 30]
    tavily_failures = [row for row in backend if any("Live search" in str(item) or "tavily" in str(item).lower() for item in row.get("failures", []))]
    gemini_failures = [row for row in backend if any("gemini" in str(item).lower() for item in row.get("failures", []))]
    payload_mismatches = [row for row in frontend if any("payload_mismatch" in item or "leaked" in item for item in row.get("failures", []))]
    summary = {
        "total_tests": len(backend) + len(frontend),
        "backend_tests": len(backend), "frontend_tests": len(frontend),
        "passed": backend_outcomes["PASS"] + frontend_outcomes["PASS"],
        "failed": backend_outcomes["FAIL"] + frontend_outcomes["FAIL"],
        "warnings": len(warnings),
        "no_relevant_schemes_found": backend_outcomes["NO_RELEVANT_SCHEMES_FOUND"],
        "needs_verification": sum(row.get("eligibility_counts", {}).get("NEEDS_VERIFICATION", 0) for row in backend),
        "frontend_failures": len(frontend_failures), "backend_failures": len(backend_failures),
        "retrieval_failures": len(retrieval_failures), "eligibility_failures": len(eligibility_failures),
        "tavily_failures": len(tavily_failures), "gemini_failures": len(gemini_failures),
        "ui_network_payload_mismatches": len(payload_mismatches), "slow_api_calls": len(slow),
    }
    verdict = "CRITICAL FAILURE" if summary["retrieval_failures"] or summary["ui_network_payload_mismatches"] else "NEEDS FIXES" if summary["failed"] else "READY WITH WARNINGS" if summary["warnings"] or summary["no_relevant_schemes_found"] else "READY"
    summary["verdict"] = verdict
    (OUTPUT / "qa_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (OUTPUT / "qa_table.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Location", "Profile", "Status", "Schemes", "Official Sources", "Eligibility Issues", "Latency"])
        for row in backend:
            writer.writerow([row.get("location"), row.get("profile"), row.get("outcome"), row.get("scheme_count"), row.get("official_source_count"), "; ".join(row.get("eligibility_issues", [])), row.get("latency_seconds")])
        for row in frontend:
            writer.writerow([row.get("location"), row.get("profile"), row.get("status"), row.get("schemes"), row.get("official_sources"), "; ".join(row.get("failures", [])), row.get("latency_seconds")])
    lines = ["# Government Scheme Navigator Live QA", "", f"## Verdict: {verdict}", ""]
    lines.extend(f"- {key.replace('_', ' ').title()}: {value}" for key, value in summary.items() if key != "verdict")
    lines.extend(["", "## Failed cases"])
    lines.extend([f"- {row.get('location')} {row.get('profile')}: {', '.join(row.get('failures', []))}" for row in backend_failures] or ["- None"])
    lines.extend([f"- Frontend {row.get('location')}: {', '.join(row.get('failures', []))}" for row in frontend_failures] or [])
    lines.extend(["", "## Slow API calls"])
    lines.extend([f"- {row.get('location')} {row.get('profile')}: {row.get('latency_seconds')}s" for row in slow] or ["- None"])
    (OUTPUT / "qa_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
