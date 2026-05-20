
from typing import Any, Optional, Tuple
import logging
from threading import RLock

from prophet import Prophet
from pathlib import Path

from adapters.base_interface import BaseModel
from adapters.adapters import ARAdapter, NaiveAdapter, ProphetAdapter, XGBoostAdapter

logger = logging.getLogger(__name__)

# ============================================================================
# Single-Entry Model Instance Cache (per worker process)
# ============================================================================
# Cache stores only the most recently requested model version in memory.
# When a new version is requested, the old entry is evicted and replaced.
# Lock protects against concurrent duplicate loads in the same process.
#
# Cache key: (normalized_model_path, model_type) uniquely identifies a model version
#

_MODEL_CACHE: dict[Tuple[str, str], Any] = {}  # { (model_path, type): model_instance }
_MODEL_CACHE_LOCK = RLock()
_CACHE_STATS = {"hits": 0, "misses": 0, "evictions": 0}  # Instrumentation


def _build_cache_key(model_rel_dirpath: Optional[str], model_type: Optional[str]) -> Tuple[str, str]:
    """
    Build a stable cache key from model path and type.
    Normalizes paths to absolute form for consistent identification.
    
    :param model_rel_dirpath: Path to model (relative or absolute, or 'none')
    :param model_type: Normalized model type ('prophet', 'xgb', 'naive', 'ar')
    :return: Tuple of (normalized_path, model_type) for cache lookup
    """
    if model_rel_dirpath == "none":
        key_path = "none"
    else:
        model_path = Path(model_rel_dirpath)
        if model_path.is_absolute():
            key_path = str(model_path)
        else:
            base_dirpath = Path("/workspace/models")
            key_path = str(base_dirpath / model_path)
    
    return (key_path, str(model_type or "").strip().lower())


def _normalize_model_type(model_type: Optional[str]) -> str:
    """Normalize model type provided by config without deriving it from model_id."""
    normalized = str(model_type or "").strip().lower()
    if normalized in {"", "null"}:
        raise ValueError("model_type must be provided in model config")
    if normalized in {"xgb", "prophet", "naive", "ar"}:
        return normalized
    raise ValueError(f"Unsupported model_type: {model_type}")


def _normalize_fallback_name(fallback: Optional[str]) -> str:
    """Normalize fallback name to a supported lowercase token."""
    normalized = str(fallback or "none").strip().lower()
    if normalized in {"", "false", "null"}:
        return "none"
    return normalized


def _build_fallback_model(fallback: str) -> Optional[BaseModel]:
    """Create fallback adapter by configured name; return None when disabled."""
    if fallback == "none":
        return None
    if fallback == "naive":
        return NaiveAdapter(model_name="naive_fallback", horizon=24)
    if fallback == "ar":
        return ARAdapter(model_name="ar_fallback")
    if fallback == "prophet":
        return ProphetAdapter(model_name="prophet_fallback")
    if fallback == "xgb":
        return XGBoostAdapter(model_name="xgb_fallback")
    raise ValueError(f"Unsupported fallback model: {fallback}")


def init_model(
    model_rel_dirpath: Optional[str],
    step: int,
    use_dynamic_normalization: bool = False,
    fallback: str = "none",
    model_type: Optional[str] = None,
) -> Any:
    """
    Initialize model by path, step and use_dynamic_normalization.
    
    Updated to use adapter pattern instead of deprecated fpforecast module.
    Includes single-entry in-memory cache per worker process for latest model version.

    :param str model_rel_dirpath: Path to model directory.
    :param int step: Step in milliseconds.
    :param bool use_dynamic_normalization: Whether to use dynamic normalization.
    :param str fallback: Fallback model type if primary load fails.
    :param str model_type: Model type identifier ('prophet', 'xgb', 'naive', 'ar').

    :return: Model instance (BaseModel or Prophet), either from cache or newly loaded.
    :rtype: Any

    :raises Exception: If model cannot be loaded and fallback is disabled.
    """

    # --- Cache Lookup ---
    # Check if we have this exact model version cached; if yes, return immediately.
    # Cache key combines model path (version identity) and type.
    cache_key = _build_cache_key(model_rel_dirpath, model_type)
    
    with _MODEL_CACHE_LOCK:
        if cache_key in _MODEL_CACHE:
            _CACHE_STATS["hits"] += 1
            cached_model = _MODEL_CACHE[cache_key]
            logger.info(
                "Model cache HIT for key=%s (total_hits=%d)",
                cache_key,
                _CACHE_STATS["hits"],
            )
            return cached_model
        else:
            _CACHE_STATS["misses"] += 1
            logger.debug(
                "Model cache MISS for key=%s (total_misses=%d)",
                cache_key,
                _CACHE_STATS["misses"],
            )
    
    # --- Cache Miss: Proceed with Model Load (within lock for atomic replace) ---
    with _MODEL_CACHE_LOCK:
        # Double-check: another thread may have loaded this version while we waited for lock
        if cache_key in _MODEL_CACHE:
            _CACHE_STATS["hits"] += 1
            cached_model = _MODEL_CACHE[cache_key]
            logger.info("Model cache HIT (double-check) for key=%s", cache_key)
            return cached_model
        
        # Still miss: load the model
        logger.info("Model cache LOAD starting for key=%s", cache_key)
        
        fallback = _normalize_fallback_name(fallback)

        if model_rel_dirpath == "none":
            logger.info("model_rel_dirpath is 'none', creating new Prophet model")

            if step == 2592000000:  # Monthly (30 days) step expected to have 12+ months of data
                seasonality_kwargs = {
                    "daily_seasonality": False,
                    "weekly_seasonality": False,
                    "yearly_seasonality": True,
                }

            elif step == 86400000:  # Daily step expected to have 30+ days of data
                seasonality_kwargs = {
                    "daily_seasonality": True,
                    "weekly_seasonality": True,
                    "yearly_seasonality": False,
                }

            elif step == 3600000:  # Hourly step expected to have 30+ days of data
                seasonality_kwargs = {
                    "daily_seasonality": True,
                    "weekly_seasonality": False,
                    "yearly_seasonality": False,
                }

            # Create new Prophet model to train on the provided inputs and no normalization
            prophet_model = Prophet(
                changepoint_prior_scale=0.1,
                changepoint_range=0.9,
                growth="flat",
                # mcmc_samples=100,
                n_changepoints=5,
                seasonality_mode="multiplicative",
                seasonality_prior_scale=30.0,
                **seasonality_kwargs
            )
            
            # Wrap Prophet model in adapter
            model = ProphetAdapter(model_name="prophet_new", legacy_model=prophet_model)

        else:
            model_type = _normalize_model_type(model_type)

            model_path = Path(model_rel_dirpath)
            if model_path.is_absolute():
                model_dirpath = model_path
            else:
                base_dirpath = Path("/workspace/models")
                model_dirpath = base_dirpath / model_path
            
            try:
                if model_type == "naive":
                    logger.info("Initializing Naive (historical replay) model")
                    horizon = 24
                    model = NaiveAdapter(model_name="naive_model", horizon=horizon)

                elif model_type == "ar":
                    logger.info("Initializing AR adapter model")
                    model = ARAdapter(model_name="ar_model")

                elif model_type == "xgb":
                    logger.info(f"Loading XGBoost model from {model_dirpath}")
                    model_filepath = model_dirpath / "xgb_model.json"
                    
                    if not model_filepath.is_file():
                        fallback_model = _build_fallback_model(fallback)
                        if fallback_model is None:
                            raise FileNotFoundError(f"Model file not found and fallback disabled: {model_filepath}")
                        logger.warning(
                            "Model file not found: %s; using configured fallback '%s'",
                            model_filepath,
                            fallback,
                        )
                        model = fallback_model
                    else:
                        logger.info(f"Loading XGBoost model from {model_filepath}")
                        # Try to load multi-step XGBoost models, wrap in adapter
                        try:
                            import json
                            import xgboost as xgb
                            
                            with open(model_filepath, 'r') as f:
                                manifest = json.load(f)
                            
                            # Load all step boosters
                            step_files = manifest.get("steps", [])
                            models_dict = {}
                            
                            for step_file in step_files:
                                booster_path = model_dirpath / step_file
                                booster = xgb.Booster()
                                booster.load_model(str(booster_path))
                                # Extract step number from filename
                                step_num = int(step_file.split("_")[-1].split(".")[0])
                                models_dict[step_num] = booster
                            
                            if not models_dict:
                                raise ValueError("No step files found in manifest")
                            
                            # Wrap loaded boosters in XGBoostAdapter
                            model = XGBoostAdapter(model_name="xgboost_model", legacy_model=models_dict)
                            model.load()
                            
                        except Exception as e:
                            fallback_model = _build_fallback_model(fallback)
                            if fallback_model is None:
                                raise
                            logger.error(
                                "Failed to load XGBoost model: %s; using configured fallback '%s'",
                                e,
                                fallback,
                            )
                            model = fallback_model

                elif model_type == "prophet":
                    logger.info(f"Loading Prophet model from {model_dirpath}")
                    model_filepath = model_dirpath / "prophet_model.json"
                    if not model_filepath.is_file():
                        legacy_model_filepath = model_dirpath / "model.prophet.json"
                        if legacy_model_filepath.is_file():
                            model_filepath = legacy_model_filepath
                    
                    if not model_filepath.is_file():
                        fallback_model = _build_fallback_model(fallback)
                        if fallback_model is None:
                            raise FileNotFoundError(f"Model file not found and fallback disabled: {model_filepath}")
                        logger.warning(
                            "Model file not found: %s; using configured fallback '%s'",
                            model_filepath,
                            fallback,
                        )
                        model = fallback_model
                    else:
                        logger.info(f"Loading Prophet model from {model_filepath}")
                        # Try to load legacy model, wrap in adapter
                        try:
                            import json
                            with open(model_filepath, 'r') as f:
                                model_data = json.load(f)
                            model = ProphetAdapter(model_name="prophet_model")
                        except Exception as e:
                            fallback_model = _build_fallback_model(fallback)
                            if fallback_model is None:
                                raise
                            logger.error(
                                "Failed to load Prophet model: %s; using configured fallback '%s'",
                                e,
                                fallback,
                            )
                            model = fallback_model
            except Exception as e:
                logger.error(f"Error initializing model: {e}")
                raise

        logger.info(f"Initialized model: {model}")
        
        # --- Cache Store: Atomic single-entry replacement ---
        # Evict old entry (if any) and store new model version
        if _MODEL_CACHE:
            old_key = list(_MODEL_CACHE.keys())[0]
            old_model = _MODEL_CACHE.pop(old_key)
            _CACHE_STATS["evictions"] += 1
            logger.info("Model cache EVICT key=%s (replaced by %s, total_evictions=%d)", old_key, cache_key, _CACHE_STATS["evictions"])
        
        _MODEL_CACHE[cache_key] = model
        logger.info("Model cache STORE key=%s (total_stored=1, hits=%d, misses=%d)", cache_key, _CACHE_STATS["hits"], _CACHE_STATS["misses"])
        
        return model

