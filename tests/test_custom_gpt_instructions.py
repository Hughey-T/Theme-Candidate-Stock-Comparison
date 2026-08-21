from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTRUCTION_FILES = [
    ROOT / "docs" / "custom-gpt-instructions.md",
    ROOT / "docs" / "custom-gpt-production-instructions.md",
]

REQUIRED_V2_OPERATIONS = {
    "getRuntimeHealth",
    "createBlindComparisonSessionV2",
    "getBlindPhaseContractV2",
    "submitBlindPhaseV2",
    "startBlindComparisonUpdateV2",
    "discloseMechanicalReconciliationV2",
    "getBlindIndividualHandoffV2",
    "acknowledgeBlindAnalysisV2",
    "getReconciliationHandoffV2",
}


def test_custom_gpt_instruction_files_are_identical() -> None:
    contents = [path.read_text(encoding="utf-8") for path in INSTRUCTION_FILES]
    assert contents[0] == contents[1]


def test_custom_gpt_instructions_pin_v2_action_flow() -> None:
    text = INSTRUCTION_FILES[0].read_text(encoding="utf-8")

    for operation in REQUIRED_V2_OPERATIONS:
        assert operation in text

    assert "contract_version` は必ず `2.0.0`" in text
    assert "旧v1 Actionが無いこと自体を停止理由にしてはいけない" in text
    assert "Idempotency-Key" in text


def test_custom_gpt_instructions_forbid_legacy_startup_contract() -> None:
    text = INSTRUCTION_FILES[0].read_text(encoding="utf-8")

    assert "`createComparisonSession`" in text
    assert '`schema_version="1.0.0"`' in text
    assert "使用しない" in text
    assert "v1へフォールバックしたりしない" in text
