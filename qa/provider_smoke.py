"""Provider health/smoke check: one tiny live call, no credential output."""

import json
import sys

from agent import llm_client


def main() -> int:
    provider = llm_client.get_provider()
    model = llm_client.get_primary_model()
    print(f"provider: {provider}")
    print(f"model: {model}")
    print(f"fallbacks: {list(llm_client.get_fallback_models())}")
    try:
        resp = llm_client.generate(
            'Reply with exactly: {"status": "ok"}',
            temperature=0.0,
            purpose="provider-smoke",
        )
    except Exception as exc:  # noqa: BLE001
        text = f"{type(exc).__name__}: {exc}".lower()
        print("provider reachable: no")
        if "quota" in text or "resource_exhausted" in text or "429" in text:
            print("quota available: no (RESOURCE_EXHAUSTED)")
        else:
            print("quota available: unknown")
        print("structured response valid: no")
        return 1

    print("provider reachable: yes")
    print("model reachable: yes")
    print("quota available: yes")
    try:
        parsed = json.loads(resp.text)
        valid = isinstance(parsed, dict)
    except Exception:  # noqa: BLE001
        valid = False
    print(f"structured response valid: {'yes' if valid else 'no'}")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
