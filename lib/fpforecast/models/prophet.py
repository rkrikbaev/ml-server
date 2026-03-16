import os
import logging
import json
from prophet import Prophet
from prophet.serialize import model_to_json, model_from_json
from pathlib import Path

from fpforecast.models.base import ModelWithMetaInfo


logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
logger = logging.getLogger(__name__)


class ModelWithMetaInfoProphet(ModelWithMetaInfo):
    def __init__(self, model_params, verbose, debug):
        super().__init__(model_params, verbose, debug)

    def save_model(self, filepath: Path):
        """Save model and meta info to filepath."""
        json_to_save = {
            'model': model_to_json(self.model),
            'model_params': self.model_params,
            'verbose': self.verbose,
            'debug': self.debug
        }
        with open(filepath, 'w') as f:
            json.dump(json_to_save, f)

    @staticmethod
    def load_model(filepath: Path):
        """Load model and meta info from filepath."""
        with open(filepath, 'r') as f:
            json_to_load = json.load(f)
        
        model_with_meta = ModelWithMetaInfoProphet(
            model_params=json_to_load['model_params'], 
            verbose=json_to_load['verbose'], 
            debug=json_to_load['debug']
        )
        model_with_meta.model = model_from_json(json_to_load['model'])
        
        return model_with_meta

    def predict(self, df):
        """Predict values for df."""
        df = df.copy()
        df_forecast = self.model.predict(df)
        return df_forecast

    def fit(self, df_train, df_val=None):
        """Train model."""
        df_train = df_train.copy()
        if df_val is not None:
            df_val = df_val.copy()

        assert 'ds' in df_train.columns, "df_train must contain 'ds' column."
        assert 'y' in df_train.columns, "df_train must contain 'y' column."
        if df_val is not None:
            assert 'ds' in df_val.columns, "df_val must contain 'ds' column."
            assert 'y' in df_val.columns, "df_val must contain 'y' column."

        self.model = Prophet(**self.model_params)

        # Add country holidays if specified
        if 'holidays_prior_scale' in self.model_params and self.model_params['holidays_prior_scale'] is not None:
            self.model.add_country_holidays(country_name='KZ')
        
        # Add all the extra columns as regressors
        for col in df_train.columns.difference(['ds', 'y']):
            self.model.add_regressor(col)
        
        self.model.fit(df_train)

        return self
