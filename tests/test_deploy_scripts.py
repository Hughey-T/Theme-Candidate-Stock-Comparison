from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = ROOT / "deploy" / "update-production.ps1"
NGROK_SCRIPT = ROOT / "deploy" / "setup-ngrok.ps1"


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


def test_update_script_preserves_shared_gateway_network() -> None:
    text = UPDATE_SCRIPT.read_text(encoding="utf-8")

    assert "GatewayNetworkName = 'local-ai-gateway'" in text
    assert "GatewayAlias = 'theme-compare'" in text
    assert "Invoke-Docker network connect --alias $GatewayAlias" in text
    assert "$GatewayNetworkName $ContainerName" in text


def test_ngrok_script_accepts_current_free_domain_suffixes() -> None:
    text = NGROK_SCRIPT.read_text(encoding="utf-8")

    assert "\\.ngrok(-free)?\\.(app|dev)$" in text


def test_ngrok_script_uses_only_central_gateway_tunnel() -> None:
    text = NGROK_SCRIPT.read_text(encoding="utf-8")

    required = [
        "GatewayPort = 8080",
        "ServicePrefix = '/theme-compare'",
        "Get-NgrokTunnelUrlForPort",
        "-Port $GatewayPort",
        "The gateway repository owns ngrok startup",
        "do not start a Theme-specific tunnel",
    ]
    for marker in required:
        assert marker in text


def test_ngrok_script_removes_legacy_theme_specific_startup() -> None:
    text = NGROK_SCRIPT.read_text(encoding="utf-8")

    required = [
        "Remove-LegacyThemeNgrokStartup",
        "ThemeCandidateStockComparison-ngrok.lnk",
        "start-ngrok.ps1",
        "no Theme-specific startup entry is created",
    ]
    for marker in required:
        assert marker in text


def test_ngrok_script_publishes_prefixed_theme_url() -> None:
    text = NGROK_SCRIPT.read_text(encoding="utf-8")

    required = [
        '$publicUrl = "$publicOrigin$servicePrefixNormalized"',
        "THEME_COMPARE_PUBLIC_URL",
        "$gatewayBase$ServicePrefix/health",
    ]
    for marker in required:
        assert marker in text


def test_ngrok_public_health_requires_v2_fingerprint() -> None:
    text = NGROK_SCRIPT.read_text(encoding="utf-8")

    required = [
        "$publicHealth.contract_version -ne '2.0.0'",
        "$publicHealth.api_profile -ne 'custom-gpt-v2'",
        "$publicHealth.schema_sha256",
    ]
    for marker in required:
        assert marker in text
