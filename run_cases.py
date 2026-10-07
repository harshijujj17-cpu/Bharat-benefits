from api.main import RecommendRequest, recommend
from rag.live_retriever import LiveSchemeRetriever
from agent.pipeline import recommend_for_profile

def run_case(name, profile):
    print(f"\n=== Case: {name} ===")
    retriever = LiveSchemeRetriever(max_queries=10)
    result = recommend_for_profile(profile, retriever=retriever, include_llm_queries=True)
    recommendations = result.get("recommendations", [])
    retrieval = result.get("retrieval") or {}
    source_urls = retrieval.get("source_urls") or []

    print(f"Recommendation count: {len(recommendations)}")
    print(f"Tavily provider: {retrieval.get('provider')}")
    print(f"Query count: {len(retrieval.get('queries') or [])}")
    print(f"Official result count: {retrieval.get('official_result_count')}")
    print("Top recommendations:")
    for rec in recommendations[:5]:
        print(f" - {rec.get('scheme_name')} ({rec.get('official_source_url')})")
    print(f"Official/Telangana/Central sources seen: {bool(source_urls)}")

def run_rejection_case():
    print("\n=== Case: non-Telangana state ===")
    payload = RecommendRequest(state="Karnataka", goal="Education", top_k=8)
    result = recommend(payload, None)
    print(result.get("notice"))
    print(f"Recommendations: {len(result.get('recommendations', []))}")

if __name__ == "__main__":
    run_case(
        "Telangana student",
        {"state": "Telangana", "goal": "Education; scholarship support", "student_status": "Yes"},
    )
    run_case(
        "Telangana farmer",
        {"state": "Telangana", "goal": "Agriculture support", "farmer_status": "Yes"},
    )
    run_case(
        "Telangana woman",
        {"state": "Telangana", "goal": "Women and child welfare support", "gender": "Female"},
    )
    run_case(
        "Telangana citizen with Central Government scheme",
        {"state": "Telangana", "goal": "Central government social security scheme"},
    )
    run_rejection_case()
