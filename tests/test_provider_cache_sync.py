"""Unit tests for MLflow provider cache sync layout and fallback behavior."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapters.provider import ModelProvider


@dataclass
class _VersionInfo:
    version: str | int | None = None
    run_id: str | None = None


class _FakeMlflowClient:
    def __init__(self, *, alias_version: str = "1", run_id: str = "run-1") -> None:
        self.alias_version = alias_version
        self.run_id = run_id
        self.download_calls = 0

    def get_model_version_by_alias(self, name: str, alias: str) -> _VersionInfo:
        return _VersionInfo(version=self.alias_version, run_id=self.run_id)

    def get_model_version(self, name: str, version: str) -> _VersionInfo:
        return _VersionInfo(version=version, run_id=self.run_id)

    def download_artifacts(self, run_id: str, artifact_path: str, dst_path: str) -> str:
        self.download_calls += 1
        target = Path(dst_path) / artifact_path
        (target / "configuration").mkdir(parents=True, exist_ok=True)
        (target / "model").mkdir(parents=True, exist_ok=True)
        (target / "configuration" / "cache_config.json").write_text("{}", encoding="utf-8")
        return str(target)


class _FailingResolveClient(_FakeMlflowClient):
    def get_model_version_by_alias(self, name: str, alias: str) -> _VersionInfo:
        raise RuntimeError("registry unavailable")


def _new_provider(tmp_path: Path, client: _FakeMlflowClient) -> ModelProvider:
    provider = ModelProvider()
    provider.cache_root = tmp_path
    provider.default_selector = "Production"
    provider.max_cached_bundles = 3
    provider._client = client
    return provider


def test_sync_writes_bundle_in_model_alias_version_layout(tmp_path: Path) -> None:
    client = _FakeMlflowClient(alias_version="7", run_id="run-777")
    provider = _new_provider(tmp_path, client)

    result = provider.sync_with_registry("root/A", "Production")

    expected_bundle = tmp_path / "root%2FA" / "Production" / "7" / "bundle"
    assert result.bundle_path == expected_bundle
    assert result.model_version == "7"
    assert result.run_id == "run-777"
    assert result.source == "mlflow"
    assert result.fallback_used is False
    assert (expected_bundle / "configuration" / "cache_config.json").is_file()
    assert client.download_calls == 1


def test_sync_skips_download_when_valid_cached_bundle_exists(tmp_path: Path) -> None:
    client = _FakeMlflowClient(alias_version="3", run_id="run-333")
    provider = _new_provider(tmp_path, client)

    bundle = tmp_path / "model-id" / "Production" / "3" / "bundle"
    (bundle / "configuration").mkdir(parents=True, exist_ok=True)
    (bundle / "model").mkdir(parents=True, exist_ok=True)
    (bundle / "configuration" / "cache_config.json").write_text("{}", encoding="utf-8")

    result = provider.sync_with_registry("model-id", "Production")

    assert result.bundle_path == bundle
    assert result.model_version == "3"
    assert result.source == "mlflow"
    assert client.download_calls == 0


def test_sync_normalizes_legacy_nested_bundle_layout_without_download(tmp_path: Path) -> None:
    client = _FakeMlflowClient(alias_version="4", run_id="run-444")
    provider = _new_provider(tmp_path, client)

    bundle = tmp_path / "legacy-model" / "Production" / "4" / "bundle"
    nested_bundle = bundle / "bundle"
    (nested_bundle / "configuration").mkdir(parents=True, exist_ok=True)
    (nested_bundle / "model").mkdir(parents=True, exist_ok=True)
    (nested_bundle / "configuration" / "cache_config.json").write_text("{}", encoding="utf-8")

    result = provider.sync_with_registry("legacy-model", "Production")

    assert result.bundle_path == bundle
    assert result.config_path == bundle / "configuration" / "cache_config.json"
    assert (bundle / "configuration" / "cache_config.json").is_file()
    assert not (bundle / "bundle").exists()
    assert client.download_calls == 0


def test_sync_uses_latest_cached_selector_bundle_on_registry_failure(tmp_path: Path) -> None:
    client = _FailingResolveClient(alias_version="8", run_id="run-888")
    provider = _new_provider(tmp_path, client)

    version_dir = tmp_path / "my-model" / "Production" / "2"
    bundle = version_dir / "bundle"
    (bundle / "configuration").mkdir(parents=True, exist_ok=True)
    (bundle / "model").mkdir(parents=True, exist_ok=True)
    (bundle / "configuration" / "cache_config.json").write_text("{}", encoding="utf-8")
    provider._write_metadata(version_dir, "my-model", "Production", "2", "run-cached")

    result = provider.sync_with_registry("my-model", "Production")

    assert result.source == "cache"
    assert result.fallback_used is True
    assert result.bundle_path == bundle
    assert result.model_version == "2"
    assert result.run_id == "run-cached"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
