from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from shutil import move
from shutil import rmtree
from tempfile import TemporaryDirectory
from typing import Any, Optional
from urllib.parse import quote
import json
import logging
import os

from mlflow.tracking import MlflowClient


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    model_id: str
    selector: str
    run_id: Optional[str]
    bundle_path: Optional[Path]
    model_path: Optional[Path]
    config_path: Optional[Path]
    source: str
    fallback_used: bool


class ModelProvider:
    def __init__(self) -> None:
        self.cache_root = Path(os.getenv("MODEL_REGISTRY_CACHE_DIR", "/tmp/mlserver_registry_cache"))
        self.default_selector = os.getenv("MLFLOW_DEFAULT_ALIAS", "Production")
        self.max_cached_bundles = int(os.getenv("MODEL_REGISTRY_CACHE_MAX", "3"))
        self._client: Optional[MlflowClient] = None

    def sync_with_registry(self, model_id: str, selector: Optional[str]) -> SyncResult:
        effective_selector = str(selector or self.default_selector)

        if model_id == "none":
            return SyncResult(
                model_id=model_id,
                selector=effective_selector,
                run_id=None,
                bundle_path=None,
                model_path=None,
                config_path=None,
                source="online",
                fallback_used=False,
            )

        latest_cached = self._find_latest_cached(model_id)

        try:
            run_id = self._resolve_run_id(model_id, effective_selector)
            cached_run_path = self._run_cache_path(model_id, effective_selector, run_id)
            bundle_path = cached_run_path / "bundle"

            if not bundle_path.is_dir():
                self._download_bundle(run_id, cached_run_path)

            self._write_metadata(cached_run_path, model_id, effective_selector, run_id)
            self._touch(cached_run_path)
            self._prune_model_cache(model_id)

            return self._build_sync_result(
                model_id=model_id,
                selector=effective_selector,
                run_id=run_id,
                bundle_path=bundle_path,
                source="mlflow",
                fallback_used=False,
            )
        except Exception as error:
            logger.warning(
                "MLflow sync failed for model_id=%s selector=%s: %s",
                model_id,
                effective_selector,
                error,
            )
            if latest_cached is not None:
                logger.warning(
                    "Using cached bundle as fallback model_id=%s path=%s",
                    model_id,
                    latest_cached,
                )
                metadata = self._read_metadata(latest_cached)
                run_id = None
                if isinstance(metadata, dict):
                    run_id = metadata.get("run_id")
                return self._build_sync_result(
                    model_id=model_id,
                    selector=effective_selector,
                    run_id=run_id,
                    bundle_path=latest_cached / "bundle",
                    source="cache",
                    fallback_used=True,
                )

            return SyncResult(
                model_id=model_id,
                selector=effective_selector,
                run_id=None,
                bundle_path=None,
                model_path=None,
                config_path=None,
                source="local",
                fallback_used=True,
            )

    def _client_instance(self) -> MlflowClient:
        if self._client is None:
            tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
            registry_uri = os.getenv("MLFLOW_REGISTRY_URI") or tracking_uri
            self._client = MlflowClient(tracking_uri=tracking_uri, registry_uri=registry_uri)
        return self._client

    def _resolve_run_id(self, model_id: str, selector: str) -> str:
        client = self._client_instance()

        if selector.isdigit():
            version = client.get_model_version(name=model_id, version=selector)
            run_id = getattr(version, "run_id", None)
            if not run_id:
                raise RuntimeError(f"Model version has no run_id: model_id={model_id} version={selector}")
            return run_id

        version_info = client.get_model_version_by_alias(model_id, selector)
        run_id = getattr(version_info, "run_id", None)
        if not run_id:
            raise RuntimeError(f"Alias has no run_id: model_id={model_id} selector={selector}")
        return run_id

    def _download_bundle(self, run_id: str, run_cache_path: Path) -> None:
        client = self._client_instance()
        run_cache_path.mkdir(parents=True, exist_ok=True)

        with TemporaryDirectory() as tmp_dir:
            local_path = Path(client.download_artifacts(run_id, "bundle", tmp_dir))
            if not local_path.is_dir():
                raise RuntimeError(f"Downloaded bundle path is not a directory: {local_path}")

            target_bundle_path = run_cache_path / "bundle"
            if target_bundle_path.exists():
                rmtree(target_bundle_path, ignore_errors=True)
            move(str(local_path), str(target_bundle_path))

    def _build_sync_result(
        self,
        model_id: str,
        selector: str,
        run_id: Optional[str],
        bundle_path: Optional[Path],
        source: str,
        fallback_used: bool,
    ) -> SyncResult:
        model_path = None
        config_path = None

        if bundle_path and bundle_path.is_dir():
            candidate_model_path = bundle_path / "model"
            if candidate_model_path.is_dir():
                model_path = candidate_model_path

            for rel_path in (
                "configuration/cache_config.json",
                "config/cache_config.json",
                "cache_config.json",
            ):
                candidate = bundle_path / rel_path
                if candidate.is_file():
                    config_path = candidate
                    break

        return SyncResult(
            model_id=model_id,
            selector=selector,
            run_id=run_id,
            bundle_path=bundle_path,
            model_path=model_path,
            config_path=config_path,
            source=source,
            fallback_used=fallback_used,
        )

    def _run_cache_path(self, model_id: str, selector: str, run_id: str) -> Path:
        return self._selector_cache_path(model_id, selector) / run_id

    def _selector_cache_path(self, model_id: str, selector: str) -> Path:
        return self._model_cache_path(model_id) / quote(selector, safe="")

    def _model_cache_path(self, model_id: str) -> Path:
        model_hash = sha1(model_id.encode("utf-8")).hexdigest()[:12]
        encoded_model_id = quote(model_id, safe="")
        return self.cache_root / f"{encoded_model_id}__{model_hash}"

    def _write_metadata(self, run_cache_path: Path, model_id: str, selector: str, run_id: str) -> None:
        payload = {
            "model_id": model_id,
            "selector": selector,
            "run_id": run_id,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        metadata_path = run_cache_path / "metadata.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def _read_metadata(self, run_cache_path: Path) -> Optional[dict[str, Any]]:
        metadata_path = run_cache_path / "metadata.json"
        if not metadata_path.is_file():
            return None
        try:
            return json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _find_latest_cached(self, model_id: str) -> Optional[Path]:
        model_cache_path = self._model_cache_path(model_id)
        if not model_cache_path.is_dir():
            return None

        candidates: list[Path] = []
        for selector_dir in model_cache_path.iterdir():
            if not selector_dir.is_dir():
                continue
            for run_dir in selector_dir.iterdir():
                if not run_dir.is_dir():
                    continue
                bundle = run_dir / "bundle"
                if bundle.is_dir():
                    candidates.append(run_dir)

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def _prune_model_cache(self, model_id: str) -> None:
        if self.max_cached_bundles <= 0:
            return

        model_cache_path = self._model_cache_path(model_id)
        if not model_cache_path.is_dir():
            return

        run_dirs: list[Path] = []
        for selector_dir in model_cache_path.iterdir():
            if not selector_dir.is_dir():
                continue
            for run_dir in selector_dir.iterdir():
                if run_dir.is_dir():
                    run_dirs.append(run_dir)

        run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for stale_dir in run_dirs[self.max_cached_bundles :]:
            rmtree(stale_dir, ignore_errors=True)

    @staticmethod
    def _touch(path: Path) -> None:
        now = datetime.now().timestamp()
        os.utime(path, (now, now))


_PROVIDER: Optional[ModelProvider] = None


def get_model_provider() -> ModelProvider:
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = ModelProvider()
    return _PROVIDER
