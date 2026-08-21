from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = ROOT / "deploy" / "update-production.ps1"


def test_update_script_has_required_safety_guards() -> None:
    text = UPDATE_SCRIPT.read_text(encoding="utf-8")

    required = [
        "git status --porcelain",
        "127.0.0.1:8000:8000",
        "contract_version -eq '2.0.0'",
        "api_profile -eq 'custom-gpt-v2'",
        "schema_sha256",
        "theme-compare:rollback-",
        "RUNTIME READY: Theme Candidate Stock Comparison v2",
        "Invoke-Docker stop $ContainerName",
        "Invoke-Docker rename $ContainerName $rollbackContainer",
        "Invoke-Docker tag $old.Image $rollbackImage",
    ]
    for marker in required:
        assert marker in text


def test_update_script_never_deletes_volumes_or_prunes() -> None:
    text = UPDATE_SCRIPT.read_text(encoding="utf-8").lower()

    forbidden = [
        "docker volume rm",
        "docker volume prune",
        "docker system prune",
        "invoke-docker volume rm",
        "invoke-docker system prune",
    ]
    for marker in forbidden:
        assert marker not in text


def test_update_script_does_not_print_environment_values() -> None:
    text = UPDATE_SCRIPT.read_text(encoding="utf-8")

    assert "Write-Host $old.Config.Env" not in text
    assert "Write-Output $old.Config.Env" not in text
