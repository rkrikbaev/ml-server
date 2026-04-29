# Mariya Polkovnikova
# 2026.03.13, 04:43 PM


from typing import Any, Optional
import logging

from prophet import Prophet
from pathlib import Path

from api.forecast.base_interface import BaseModel
from api.forecast.adapters import ARAdapter, NaiveAdapter, ProphetAdapter, XGBoostAdapter

logger = logging.getLogger(__name__)


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

    :param str model_rel_dirpath: Path to model directory.
    :param int step: Step in milliseconds.
    :param bool use_dynamic_normalization: Whether to use dynamic
        normalization.

    :return: Model instance (BaseModel or Prophet).
    :rtype: Any

    :raises Exception: If the model is not dinamically normalized.
    """

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

        base_dirpath = Path("/workspace/models")
        model_rel_dirpath = Path(model_rel_dirpath)

        model_dirpath = base_dirpath / model_rel_dirpath
        
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
                    logger.info(f"Loading AR model from {model_filepath}")
                    # Try to load legacy model, wrap in adapter
                    try:
                        import json
                        with open(model_filepath, 'r') as f:
                            model_data = json.load(f)
                        model = ARAdapter(model_name="ar_model")
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

    return model

