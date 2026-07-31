from __future__ import annotations
import zipfile
from collections import Counter
from pathlib import Path


def test_docker_is_non_root_factory_healthcheck_and_constrained():
    docker = Path("Dockerfile").read_text()
    assert "USER runtime" in docker and "HEALTHCHECK" in docker
    assert "PIP_CONSTRAINT=constraints-dev.txt" in docker and 'theme-compare", "serve"' in docker
    assert "theme_compare.api:app_factory" in Path("src/theme_compare/cli.py").read_text()


def test_wheel_configuration_does_not_force_include_schema_package_twice():
    config = Path("pyproject.toml").read_text()
    assert "force-include" not in config


def assert_schema_wheel_contents(wheel: Path):
    names = zipfile.ZipFile(wheel).namelist()
    schemas = [name for name in names if name.startswith("theme_compare/schemas/")]
    counts = Counter(schemas)
    assert schemas and all(count == 1 for count in counts.values())
    expected = {
        f"theme_compare/schemas/{path.name}"
        for path in Path("src/theme_compare/schemas").glob("*")
        if path.is_file()
    }
    assert set(schemas) == expected
