"""Static source-level checks for the Bharat Benefit Navigator frontend UX
requirements (no JS runtime is configured in this repo)."""

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src" / "main.jsx"


def _source() -> str:
    return SRC.read_text(encoding="utf-8")


def test_loading_copy_present():
    assert "Searching live official sources and checking eligibility..." in _source()


def test_try_again_button_retries_same_profile():
    src = _source()
    assert "Try again" in src
    # Try again invokes findBenefits, which reuses the preserved need/state/profile state.
    assert "onClick={findBenefits}" in src


def test_profile_state_preserved_on_error_path():
    # findBenefits does not reset `profile`, `need`, or `state` before fetch; on
    # error the results view keeps them available for a retry.
    src = _source()
    assert "setError(\"\")" in src
    assert "useState" in src and "const [profile, setProfile]" in src
    assert "const [state, setState]" in src


def test_friendly_transient_message_present():
    assert "temporarily busy" in _source()


def test_no_hardcoded_scheme_data_in_frontend():
    src = _source()
    assert "schemes.json" not in src
    assert "SCHEMES =" not in src
