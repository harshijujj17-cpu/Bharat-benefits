"""Run 12 Telangana test profiles through the agent and print a clear summary.

Usage:
    python run_test_profiles.py
"""

import io
import json
import os
import sys
from pathlib import Path
from typing import Any

# Force UTF-8 output on Windows to handle currency symbols
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── ensure project root is importable ────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from agent.pipeline import recommend_for_profile
from agent.profile_normalize import normalize_profile

# ── 12 Test profiles (structured from the natural-language descriptions) ─────
TEST_PROFILES = [
    {
        "profile_id": "T01",
        "description": "16-year-old girl, school student, Telangana, OBC, income Rs.1,20,000",
        "demographics": {"age": 16, "gender": "girl", "state": "Telangana"},
        "financial_information": {"annual_household_income_inr": 120000},
        "education": {"currently_enrolled": True, "level": "school"},
        "occupation": "school student",
        "social_category": "OBC",
        "disability": False,
        "farmer": False,
    },
    {
        "profile_id": "T02",
        "description": "21-year-old woman, B.Tech student, Telangana, OBC, income Rs.2,50,000",
        "demographics": {"age": 21, "gender": "woman", "state": "Telangana"},
        "financial_information": {"annual_household_income_inr": 250000},
        "education": {"currently_enrolled": True, "level": "B.Tech"},
        "occupation": "college student",
        "social_category": "OBC",
        "disability": False,
        "farmer": False,
    },
    {
        "profile_id": "T03",
        "description": "30-year-old woman, homemaker, Telangana, SC, income Rs.1,50,000",
        "demographics": {"age": 30, "gender": "woman", "state": "Telangana"},
        "financial_information": {"annual_household_income_inr": 150000},
        "education": {"currently_enrolled": False},
        "occupation": "homemaker",
        "social_category": "SC",
        "disability": False,
        "farmer": False,
    },
    {
        "profile_id": "T04",
        "description": "35-year-old man, farmer, Telangana, OBC, income Rs.1,50,000",
        "demographics": {"age": 35, "gender": "man", "state": "Telangana"},
        "financial_information": {"annual_household_income_inr": 150000},
        "education": {"currently_enrolled": False},
        "occupation": "farmer",
        "social_category": "OBC",
        "disability": False,
        "farmer": True,
    },
    {
        "profile_id": "T05",
        "description": "45-year-old woman, farmer, Telangana, SC, income Rs.2,00,000",
        "demographics": {"age": 45, "gender": "woman", "state": "Telangana"},
        "financial_information": {"annual_household_income_inr": 200000},
        "education": {"currently_enrolled": False},
        "occupation": "farmer",
        "social_category": "SC",
        "disability": False,
        "farmer": True,
    },
    {
        "profile_id": "T06",
        "description": "32-year-old man, self-employed, Telangana, SC, disabled, income Rs.1,80,000",
        "demographics": {"age": 32, "gender": "man", "state": "Telangana"},
        "financial_information": {"annual_household_income_inr": 180000},
        "education": {"currently_enrolled": False},
        "occupation": "self-employed",
        "social_category": "SC",
        "disability": True,
        "farmer": False,
    },
    {
        "profile_id": "T07",
        "description": "60-year-old woman, retired, Telangana, General, income Rs.1,50,000",
        "demographics": {"age": 60, "gender": "woman", "state": "Telangana"},
        "financial_information": {"annual_household_income_inr": 150000},
        "education": {"currently_enrolled": False},
        "occupation": "retired",
        "social_category": "General",
        "disability": False,
        "farmer": False,
    },
    {
        "profile_id": "T08",
        "description": "70-year-old man, retired, Telangana, OBC, income Rs.1,00,000",
        "demographics": {"age": 70, "gender": "man", "state": "Telangana"},
        "financial_information": {"annual_household_income_inr": 100000},
        "education": {"currently_enrolled": False},
        "occupation": "retired",
        "social_category": "OBC",
        "disability": False,
        "farmer": False,
    },
    {
        "profile_id": "T09",
        "description": "28-year-old woman, small business owner, Telangana, OBC, income Rs.3,00,000",
        "demographics": {"age": 28, "gender": "woman", "state": "Telangana"},
        "financial_information": {"annual_household_income_inr": 300000},
        "education": {"currently_enrolled": False},
        "occupation": "self-employed / small business owner",
        "social_category": "OBC",
        "disability": False,
        "farmer": False,
    },
    {
        "profile_id": "T10",
        "description": "40-year-old man, farmer, Telangana, SC, income Rs.80,000",
        "demographics": {"age": 40, "gender": "man", "state": "Telangana"},
        "financial_information": {"annual_household_income_inr": 80000},
        "education": {"currently_enrolled": False},
        "occupation": "farmer",
        "social_category": "SC",
        "disability": False,
        "farmer": True,
    },
    {
        "profile_id": "T11",
        "description": "25-year-old woman, unemployed, Telangana, SC, disabled, income Rs.1,00,000",
        "demographics": {"age": 25, "gender": "woman", "state": "Telangana"},
        "financial_information": {"annual_household_income_inr": 100000},
        "education": {"currently_enrolled": False},
        "occupation": "unemployed",
        "social_category": "SC",
        "disability": True,
        "farmer": False,
    },
    {
        "profile_id": "T12",
        "description": "50-year-old man, farmer, Telangana, General, income Rs.1,20,000",
        "demographics": {"age": 50, "gender": "man", "state": "Telangana"},
        "financial_information": {"annual_household_income_inr": 120000},
        "education": {"currently_enrolled": False},
        "occupation": "farmer",
        "social_category": "General",
        "disability": False,
        "farmer": True,
    },
]

FACTORS = {
    "T01": "Young age + girl + student + low income + OBC",
    "T02": "College student + woman + OBC + low income",
    "T03": "Woman + SC + low income",
    "T04": "Farmer + OBC + low income",
    "T05": "Female farmer + SC + income",
    "T06": "Disability + SC + low income + employment",
    "T07": "Older adult + retired + low income",
    "T08": "Senior citizen + OBC + very low income",
    "T09": "Woman entrepreneur + OBC",
    "T10": "Farmer + SC + very low income",
    "T11": "Unemployed + woman + SC + disability + low income",
    "T12": "Farmer + General + low income",
}

SEP = "-" * 72


def run_tests():
    print("\n" + "=" * 72)
    print("  TELANGANA WELFARE SCHEME AGENT -- LIVE RETRIEVAL TEST RUN")
    print("=" * 72 + "\n")

    all_results = []
    passed = 0
    failed = 0

    for idx, profile in enumerate(TEST_PROFILES, start=1):
        pid = profile["profile_id"]
        print(f"\n{SEP}")
        print(f"  Profile #{idx} [{pid}]")
        print(f"  >> {profile['description']}")
        print(f"  >> Factors: {FACTORS[pid]}")
        print(SEP)

        # Strip test metadata before passing to agent
        agent_profile = normalize_profile(
            {k: v for k, v in profile.items() if k not in {"profile_id", "description"}}
        )

        try:
            result = recommend_for_profile(agent_profile, top_k=3)
            recommendations = result.get("recommendations", [])
            print(
                f"  [RETRIEVE] Live search queries: {result.get('retrieval', {}).get('queries')}"
            )

            print(f"  [OK] Got {len(recommendations)} recommendation(s):")
            for i, rec in enumerate(recommendations, start=1):
                scheme_name = rec.get("scheme_name", "Unknown")
                explanation = rec.get("relevance_explanation", "")
                missing = rec.get("missing_information", [])
                benefits = rec.get("benefits", "")
                source = rec.get("official_source_url") or rec.get("official_source", "")

                print(f"\n    [{i}] {scheme_name}")
                print(f"        Explanation: {explanation[:200]}{'...' if len(explanation) > 200 else ''}")
                if benefits:
                    b_str = str(benefits)
                    print(f"        Benefits: {b_str[:150]}{'...' if len(b_str) > 150 else ''}")
                if source:
                    print(f"        Source: {source}")
                if missing:
                    print(f"        Missing info: {'; '.join(missing[:2])}")

            result_entry = {
                "profile_id": pid,
                "description": profile["description"],
                "status": "ok",
                "recommended_schemes": [r.get("scheme_name") for r in recommendations],
            }
            all_results.append(result_entry)
            passed += 1

        except Exception as exc:
            print(f"  [ERROR] {type(exc).__name__}: {exc}")
            all_results.append({
                "profile_id": pid,
                "status": "error",
                "error": str(exc),
            })
            failed += 1

    # Summary
    print("\n\n" + "=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    print(f"  Passed : {passed}/{len(TEST_PROFILES)}")
    print(f"  Failed : {failed}/{len(TEST_PROFILES)}")
    print()
    print(f"  {'#':<4}  {'Profile':<6}  {'Status':<10}  Recommended Schemes")
    print(f"  {'-'*4}  {'-'*6}  {'-'*10}  {'-'*40}")
    for i, r in enumerate(all_results, start=1):
        status = r.get("status", "?")
        schemes = ", ".join(r.get("recommended_schemes", [])) or r.get("error", "---")
        print(f"  {i:<4}  {r['profile_id']:<6}  {status:<10}  {schemes[:55]}")
    print("\n" + "=" * 72 + "\n")

    # Save results
    out_path = PROJECT_ROOT / "test_12_telangana_results.json"
    out_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Full results saved to: {out_path.name}\n")


if __name__ == "__main__":
    run_tests()
