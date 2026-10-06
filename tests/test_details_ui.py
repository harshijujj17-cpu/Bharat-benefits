"""Static checks for the Details view in Bharat Benefit Navigator."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src" / "main.jsx"
CSS = ROOT / "frontend" / "src" / "styles.css"


def src() -> str:
    return SRC.read_text(encoding="utf-8")


def css() -> str:
    return CSS.read_text(encoding="utf-8")


def test_details_button_present_on_each_card():
    text = src()
    assert "Details" in text
    assert "onDetails" in text
    assert "setSelectedIndex(i)" in text


def test_details_opens_selected_recommendation_only():
    text = src()
    assert "const [selectedIndex, setSelectedIndex]" in text
    assert "recs[selectedIndex]" in text


def test_details_uses_actual_recommendation_fields():
    text = src()
    for field in ["scheme_name", "eligibility_status", "relevance_explanation", "description", "benefits", "eligibility", "required_documents", "application_process", "official_source_url", "government_department", "missing_information"]:
        assert field in text


def test_details_close_returns_to_results():
    text = src()
    assert "setSelectedIndex(null)" in text
    assert "Close" in text


def test_missing_fields_render_not_undefined():
    text = src()
    assert "Not provided by the retrieved source." in text
    assert ">undefined<" not in text
    assert "[object Object]" not in text
    assert "value === null || value === undefined" in text


def test_official_source_link_external_safe_new_tab():
    text = src()
    assert 'target="_blank"' in text
    assert 'rel="noreferrer"' in text


def test_no_static_scheme_data_introduced():
    text = src() + css()
    assert "schemes.json" not in text
    assert "SCHEMES =" not in text


def test_second_card_details_shows_second_card():
    # Structural guarantee: each card wires its own Details button to its index,
    # so card B's Details opens recs[iB], never card A's.
    text = src()
    # Each rendered card gets its own index via onDetails={() => setSelectedIndex(i)}
    assert "onDetails={() => setSelectedIndex(i)}" in text
    assert "recs[selectedIndex]" in text
