import json
import xgboost as xgb
import pandas as pd
import numpy as np
import dataclasses
import os
import logging
from pathlib import Path
from typing import List, Literal

from fpforecast.models.base import ModelWithMetaInfo
from fpforecast.features import make_features, FeatureInfo


logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
logger = logging.getLogger(__name__)


def normalize(df, mean=None, std=None):
    """Normalize df to zero mean and unit variance."""
    if mean is None:
        mean = df.mean()
    if std is None:
        std = df.std()

    df_normalized = (df - mean) / std

    return df_normalized, mean, std


def get_rel_start_or_end(feature_data: np.ndarray, is_start: bool) -> np.ndarray:
    if not is_start:
        feature_data = feature_data[:, ::-1]
    
    initial_state = feature_data[:, 0:1]
    is_different_state = feature_data != initial_state
    no_change_mask = np.all(is_different_state, axis=1)
        
    first_change_rel_pos = np.where(
        no_change_mask,
        np.nan,
        np.argmax(is_different_state, axis=1) / feature_data.shape[1]
    )[:, None]
    
    return first_change_rel_pos


def prepare_X_y(
    df, 
    col_y,
    features_info: List[FeatureInfo],
    W_past, 
    W_future,
    drop_nan_y,
):
    """Prepare X and y for AR model."""
    col_to_index = {col: i for i, col in enumerate(df.columns)}
    data = df.values  # (N, F)
    data = np.lib.stride_tricks.sliding_window_view(
        data,
        window_shape=W_past + W_future,
        axis=0
    )  # (N - W + 1, F, W)

    X_list = []
    for feature_info in features_info:
        col_idx = col_to_index[feature_info.name]

        if feature_info.span == 'past':
            feature_data = data[:, col_idx, :W_past]  # (N - W + 1, W_past)
        else:
            assert feature_info.span == 'future'
            feature_data = data[:, col_idx, -W_future:]  # (N - W + 1, W_future)
        
        if feature_info.agg == 'full':
            if feature_info.cycle_h is not None:
                feature_data = feature_data[:, ::feature_info.cycle_h]
        elif feature_info.agg == 'first':
            if feature_info.cycle_h is not None:
                feature_data = feature_data[:, ::feature_info.cycle_h]
            else:
                feature_data = feature_data[:, :1]
        elif feature_info.agg == 'last':
            if feature_info.cycle_h is not None:
                feature_data = feature_data[:, -1::feature_info.cycle_h]
            else:
                feature_data = feature_data[:, -1:]
        elif feature_info.agg == 'n_intervals':
            assert feature_info.cycle_h is None, \
                "Cycle is not supported for this aggregation"
            # Number of state changes from previous
            diff = np.diff(feature_data, axis=1) != 0
            feature_data = diff.sum(axis=1, keepdims=True)
        elif feature_info.agg == 'rel_start':
            # First state change along axis 1 index / axis 1 len
            assert feature_info.cycle_h is None, \
                "Cycle is not supported for this aggregation"
            feature_data = get_rel_start_or_end(feature_data, is_start=True)
        elif feature_info.agg == 'rel_end':
            assert feature_info.cycle_h is None, \
                "Cycle is not supported for this aggregation"
            feature_data = get_rel_start_or_end(feature_data, is_start=False)
        elif feature_info.agg == 'share':
            assert feature_info.cycle_h is None, \
                "Cycle is not supported for this aggregation"
            feature_data = feature_data.mean(axis=1, keepdims=True)
        elif feature_info.agg == 'integral':
            assert feature_info.cycle_h is None, \
                "Cycle is not supported for this aggregation"
            feature_data = feature_data.sum(axis=1, keepdims=True)
        else:
            raise ValueError(f'Unknown agg: {feature_info.agg}')

        X_list.append(feature_data)
    X = np.concatenate(X_list, axis=1)  # (N - W + 1, W_past * F_past + W_future * F_future)

    y_col_idx = col_to_index[col_y]
    y = data[:, y_col_idx, -W_future:]  # (N - W + 1, W_future)

    if drop_nan_y:
        mask = ~np.isnan(y).any(axis=1)
        X = X[mask]
        y = y[mask]

    return X, y


class ModelWithMetaInfoAr(ModelWithMetaInfo):
    def __init__(self, W_past, W_future, model_params, early_stopping_rounds, num_boost_round, verbose, debug, missing_features_strategy: Literal['coerce', 'error'] = 'coerce'):
        super().__init__(model_params, verbose, debug)

        self.mean = None
        self.std = None
        self.features_info = None

        self.W_past = W_past
        self.W_future = W_future
        self.early_stopping_rounds = early_stopping_rounds
        self.num_boost_round = num_boost_round
        self.missing_features_strategy = missing_features_strategy

    def save_model(self, filepath: Path):
        """Save model and meta info to filepath."""
        if self.model is None:
            raise ValueError("Model is not trained yet.")
        
        meta_info = self.__dict__.copy()
        del meta_info['model']
        meta_info['features_info'] = [dataclasses.asdict(feature_info) for feature_info in meta_info['features_info']]
        meta_info['mean'] = meta_info['mean'].to_dict()
        meta_info['std'] = meta_info['std'].to_dict()
        meta_info = json.dumps(meta_info)
        
        self.model.set_attr(meta_info=meta_info)
        self.model.save_model(filepath)
        self.model.set_attr(meta_info=None)  # Clean up to avoid side effects

    @staticmethod
    def load_model(filepath: Path):
        """Load model and meta info from filepath."""
        model = xgb.Booster()
        model.load_model(filepath)

        meta_info_json = model.attr('meta_info')
        meta_info = json.loads(meta_info_json)

        model_with_meta = ModelWithMetaInfoAr(
            W_past=meta_info['W_past'],
            W_future=meta_info['W_future'],
            model_params=meta_info['model_params'],
            early_stopping_rounds=meta_info['early_stopping_rounds'],
            num_boost_round=meta_info['num_boost_round'],
            verbose=meta_info['verbose'],
            debug=meta_info['debug'],
            # For backward compatibility, default to 'coerce' if not present
            missing_features_strategy=meta_info.get('missing_features_strategy', 'coerce'),
        )

        model_with_meta.model = model
        model_with_meta.mean = pd.Series(meta_info['mean'])
        model_with_meta.std = pd.Series(meta_info['std'])
        model_with_meta.features_info = [FeatureInfo(**fi) for fi in meta_info['features_info']]

        return model_with_meta
    
    def _get_y_past(self, X) -> np.ndarray | None:
        """Extract past y values from X."""
        start_idx = 0
        for feature_info in self.features_info:
            if feature_info.name == 'value':
                assert feature_info.agg == 'full', "Only 'full' agg is supported for past values."
                assert feature_info.cycle_h == 1
                assert feature_info.span == 'past'
                y_past = X[:, start_idx:start_idx + self.W_past]
                return y_past
            else:
                if feature_info.span == 'past':
                    W_feature = self.W_past
                else:
                    W_feature = self.W_future
                n_features = W_feature
                if feature_info.agg != 'full':
                    n_features = 1
                if feature_info.cycle_h is not None:
                    W_feature = n_features * feature_info.cycle_h
                start_idx += W_feature
        return None
    
    def _predict(self, df, **_kwargs):
        """Predict values for df."""
        df = df.copy()

        # Make features
        df, _ = make_features(df)

        # Explicitly add missing features with NaN values
        missing_features = [feature_info.name for feature_info in self.features_info if feature_info.name not in df.columns]
        if self.missing_features_strategy == 'error' and missing_features:
            raise ValueError(f'Missing features for prediction: {missing_features}')
        elif self.missing_features_strategy == 'coerce' and missing_features:
            df_missing_features = pd.DataFrame({feature: np.nan for feature in missing_features}, index=df.index)
            df = pd.concat([df, df_missing_features], axis=1)  # To avoid PerformanceWarning
            logger.debug(f'Missing features for AR model: {missing_features}')
        else:
            if self.missing_features_strategy not in ['error', 'coerce']:
                raise ValueError(f'Unknown missing_features_strategy: {self.missing_features_strategy}')
        
        df_normalized, _, _ = normalize(df, mean=self.mean, std=self.std)
        X, y = prepare_X_y(
            df_normalized,
            col_y='value',
            features_info=self.features_info,
            W_past=self.W_past,
            W_future=self.W_future,
            drop_nan_y=False,
        )

        is_matching = True
        start_idx = 0
        for feature_info in self.features_info:
            n_features = self.W_past if feature_info.span == 'past' else self.W_future
            if feature_info.agg != 'full':
                n_features = 1
            
            if feature_info.name == 'value':
                val_features = X[:, start_idx : start_idx + n_features]
                # Если хотя бы одно значение выходит за 3 сигмы (в нормированном виде это >3 или <-3)
                # Игнорируем NaN значения при проверке
                non_nan_mask = ~np.isnan(val_features)
                if non_nan_mask.any() and np.any(np.abs(val_features[non_nan_mask]) > 3):
                    is_matching = False
                break 
            start_idx += n_features

        dmatrix = xgb.DMatrix(X, label=np.zeros_like(y))  # Dummy labels to avoid nan issues

        y_pred_normalized = self.model.predict(dmatrix)
        
        y_pred = y_pred_normalized * self.std['value'] + self.mean['value']
        y = y * self.std['value'] + self.mean['value']

        y_past = self._get_y_past(X)
        if y_past is not None:
            y_past = y_past * self.std['value'] + self.mean['value']
        
        return y_past, y, y_pred , is_matching

    def predict(self, df, **kwargs):
        _, y, y_pred, is_matching = self._predict(df, **kwargs)
        return y, y_pred, is_matching
    
    def fit(self, df_train, df_val):
        """Train AR model using XGBoost."""
        df_train, df_val = df_train.copy(), df_val.copy()

        df_train, features_info = make_features(df_train)
        df_val, _ = make_features(df_val)
        logger.debug(f'Using features: {features_info}')

        df_train_normalized, mean, std = normalize(df_train)
        df_val_normalized, _, _ = normalize(df_val, mean=mean, std=std)

        X_train, y_train = prepare_X_y(
            df_train_normalized,
            col_y='value',
            features_info=features_info,
            W_past=self.W_past,
            W_future=self.W_future,
            drop_nan_y=True,
        )
        logger.debug(f'Training data shape: X={X_train.shape}, y={y_train.shape}')
        if self.debug:
            X_train = X_train[:1000]
            y_train = y_train[:1000]

        X_val, y_val = prepare_X_y(
            df_val_normalized,
            col_y='value',
            features_info=features_info,
            W_past=self.W_past,
            W_future=self.W_future,
            drop_nan_y=True,
        )

        if X_train.size == 0 or X_val.size == 0:
            raise ValueError("Not enough data to train the model after preparing X and y.")

        dtrain = xgb.DMatrix(X_train, label=y_train)
        dvalid = xgb.DMatrix(X_val, label=y_val)

        evallist = [(dvalid, 'eval')]

        model = xgb.train(
            self.model_params, 
            dtrain, 
            evals=evallist, 
            maximize=False, 
            early_stopping_rounds=self.early_stopping_rounds, 
            num_boost_round=self.num_boost_round, 
            verbose_eval=self.verbose,
        )

        self.model = model
        self.mean = mean
        self.std = std
        self.features_info = features_info

        return self

