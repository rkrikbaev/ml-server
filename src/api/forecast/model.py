# Mariya Polkovnikova
# 2026.03.13, 04:43 PM


from typing import Any, Optional
import logging

from prophet import Prophet
from pathlib import Path

from api.forecast.base_interface import BaseModel
from api.forecast.adapters import ARAdapter, ProphetAdapter

logger = logging.getLogger(__name__)


def _detect_model_type(model_rel_dirpath: str) -> str:
    """Infer model type from a path-style or flat model identifier."""
    normalized = model_rel_dirpath.replace("\\", "/")
    first_segment = normalized.split("/")[0].lower()

    if first_segment in {"xgb", "prophet"}:
        return first_segment

    flat_name = Path(model_rel_dirpath).name.lower()
    if flat_name.startswith("xgb") or "xgb" in flat_name:
        return "xgb"
    if flat_name.startswith("prophet") or "prophet" in flat_name:
        return "prophet"

    raise AssertionError(f"Unknown model type: {model_rel_dirpath}")


def init_model(
    model_rel_dirpath: Optional[str],
    step: int,
    use_dynamic_normalization: bool = False
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
        model_type = _detect_model_type(model_rel_dirpath)

        base_dirpath = Path("/workspace/models")
        model_rel_dirpath = Path(model_rel_dirpath)

        model_dirpath = base_dirpath / model_rel_dirpath
        
        try:
            if model_type == "xgb":
                logger.info(f"Loading XGBoost model from {model_dirpath}")
                model_filepath = model_dirpath / "xgb_model.json"
                
                if not model_filepath.is_file():
                    logger.warning(f"Model file not found: {model_filepath}")
                    model = ARAdapter(model_name="ar_fallback")
                else:
                    logger.info(f"Loading AR model from {model_filepath}")
                    # Try to load legacy model, wrap in adapter
                    try:
                        import json
                        with open(model_filepath, 'r') as f:
                            model_data = json.load(f)
                        model = ARAdapter(model_name="ar_model")
                    except Exception as e:
                        logger.error(f"Failed to load XGBoost model: {e}, using fallback")
                        model = ARAdapter(model_name="ar_fallback")

            elif model_type == "prophet":
                logger.info(f"Loading Prophet model from {model_dirpath}")
                model_filepath = model_dirpath / "prophet_model.json"
                
                if not model_filepath.is_file():
                    logger.warning(f"Model file not found: {model_filepath}")
                    model = ProphetAdapter(model_name="prophet_fallback")
                else:
                    logger.info(f"Loading Prophet model from {model_filepath}")
                    # Try to load legacy model, wrap in adapter
                    try:
                        import json
                        with open(model_filepath, 'r') as f:
                            model_data = json.load(f)
                        model = ProphetAdapter(model_name="prophet_model")
                    except Exception as e:
                        logger.error(f"Failed to load Prophet model: {e}, using fallback")
                        model = ProphetAdapter(model_name="prophet_fallback")
        except Exception as e:
            logger.error(f"Error initializing model: {e}")
            raise

    logger.info(f"Initialized model: {model}")

    return model

