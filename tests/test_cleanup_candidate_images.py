from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "cleanup-old-rollbacks.ps1"


def test_cleanup_automatically_protects_referenced_candidate_images() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    required = [
        "[string]$CurrentContainerName = 'theme-compare'",
        "reference=$ImageRepository`:candidate-*",
        "Get-ContainerImageId",
        "Get-ImageIdForTag",
        "$protectedImageIds",
        "$rollbackTargetContainerNames -contains $name",
        "Protected candidate tags:",
        "Delete unreferenced candidate tags:",
        "Removing unreferenced candidate image tag:",
        "surviving containers",
        "retained rollback generation(s)",
        "DRY RUN ONLY. No Docker object was deleted.",
    ]
    for marker in required:
        assert marker in text


def test_cleanup_avoids_prune_and_protected_resource_deletion() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()

    forbidden = [
        "docker volume rm",
        "docker volume prune",
        "docker network rm",
        "docker network prune",
        "docker system prune",
        "docker image prune",
        "docker rm theme-compare ",
        "docker rm -f theme-compare",
    ]
    for marker in forbidden:
        assert marker not in text

    assert "theme-compare-data" in text
    assert "local-ai-gateway" in text
