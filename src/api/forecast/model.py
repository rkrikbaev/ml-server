# Mariya Polkovnikova
# 2026.03.13, 04:43 PM


from typing import Any, Optional

from prophet import Prophet
from pathlib import Path

from fpforecast.models.ar import ModelWithMetaInfoAr
from fpforecast.models.prophet import ModelWithMetaInfoProphet


class SbreModel:
    pass


def init_model(
    model_rel_dirpath: Optional[str],
    step: int,
    use_dynamic_normalization: bool = False
) -> Any:
    """
    Initialize model by path, step and use_dynamic_normalization.

    :param str model_rel_dirpath: Path to model directory.
    :param int step: Step in milliseconds.
    :param bool use_dynamic_normalization: Whether to use dynamic
        normalization.

    :return: Model instance.
    :rtype: Any

    :raises Exception: If the model is not dinamically normalized.
    """

    if model_rel_dirpath == "none":
        print("model_rel_dirpath is \"none\"")

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
        model = Prophet(
            changepoint_prior_scale=0.1,
            changepoint_range=0.9,
            growth="flat",
            # mcmc_samples=100,
            n_changepoints=5,
            seasonality_mode="multiplicative",
            seasonality_prior_scale=30.0,
            **seasonality_kwargs
        )

    elif model_rel_dirpath == "sbre":
        print("model_rel_dirpath is \"sbre\"")
        model = SbreModel()

    else:
        model_type = model_rel_dirpath.split("/")[0]
        assert model_type in ["xgb", "prophet"]

        base_dirpath = Path("/workspace/models")
        model_rel_dirpath = Path(model_rel_dirpath)

        model_dirpath = base_dirpath / model_rel_dirpath
        if model_type == "xgb":
            print(f"Trying to loading xgb model from {model_dirpath}")
            model_filepath = model_dirpath / "xgb_model.json"
            model_class = ModelWithMetaInfoAr

        elif model_type == "prophet":
            print(f"Trying to loading prophet model from {model_dirpath}")
            model_filepath = model_dirpath / "prophet_model.json"
            model_class = ModelWithMetaInfoProphet

        if not model_filepath.is_file():
            print(f"Model file not found: {model_filepath}")
            model = None

        else:
            print(f"Loading model from {model_filepath}")
            model = model_class.load_model(model_filepath)

    print(f"Initialized model: {model}")

    # Set dynamic normalization if requested and supported
    try:
        if use_dynamic_normalization and isinstance(model, ModelWithMetaInfoAr):
            model.use_dynamic_normalization = True
    except Exception:
        pass

    return model
