from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS = ROOT / "docs" / "custom-gpt-instructions.md"


def test_gpt_instructions_follow_runtime_submission_requirements() -> None:
    text = INSTRUCTIONS.read_text(encoding="utf-8")

    assert "`submission_requirements` を正本として従う" in text
    assert "read and obey `submission_requirements`" in text
    assert "`candidate_transition`" in text
    assert "`evidence_as_of_max`" in text
    assert "`independent_ai_ranking_policy=submit_once_and_freeze`" in text
    assert "omit `independent_ai_ranking`" in text
    assert "Never derive it from the user-facing ranking text" in text
