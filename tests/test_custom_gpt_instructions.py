from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTRUCTION_FILES = [
    ROOT / "docs" / "custom-gpt-instructions.md",
    ROOT / "docs" / "custom-gpt-production-instructions.md",
]

REQUIRED_V2_OPERATIONS = {
    "getRuntimeHealth",
    "createBlindComparisonSessionV2",
    "recoverBlindComparisonSessionV2",
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
    assert "query parameter `idempotency_key`" in text
    assert "`Idempotency-Key` ヘッダーを要求しない" in text
    assert "同じ `idempotency_key` で `recoverBlindComparisonSessionV2` を1回だけ呼ぶ" in text


def test_custom_gpt_instructions_require_timezone_aware_rfc3339() -> None:
    text = INSTRUCTION_FILES[0].read_text(encoding="utf-8")

    assert "complete timezone-aware RFC 3339 instant" in text
    assert "Never send a bare `YYYY-MM-DD` date" in text
    assert "T00:00:00Z" in text
    assert "source_cutoff_at <= analysis_as_of" in text
    assert "Every evidence record `as_of`" in text


def test_custom_gpt_instructions_require_current_turn_action_evidence() -> None:
    text = INSTRUCTION_FILES[0].read_text(encoding="utf-8")

    assert "現在ターンに実際のAction tool call結果が存在しない限り" in text
    assert "過去ターンや旧会話のAction失敗を現在ターンの結果として再利用" in text
    assert "`createBlindComparisonSessionV2` を実際に呼ぶ" in text
    assert "現在ターンで実行した `createBlindComparisonSessionV2` のtool result" in text
    assert "Actionを実行できなかった" in text
    assert "再送を求めず未実行であることを正確に報告" in text


def test_custom_gpt_instructions_forbid_legacy_startup_contract() -> None:
    text = INSTRUCTION_FILES[0].read_text(encoding="utf-8")

    assert "`createComparisonSession`" in text
    assert '`schema_version="1.0.0"`' in text
    assert "使用しない" in text
    assert "v1へフォールバックしたりしない" in text
