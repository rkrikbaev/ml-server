#!/usr/bin/env python3
"""
Test Model Setup and Initialization Script

This script:
1. Creates a synthetic test dataset
2. Trains a Prophet model on the test data
3. Registers the model in MLflow
4. Sets up the test environment

Generated: 20.04.2026
"""

import os
import json
import logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from pathlib import Path
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def create_synthetic_data(days: int = 30, freq: str = 'h') -> pd.DataFrame:
    """
    Create synthetic time series data for testing.
    
    Args:
        days: Number of days of historical data
        freq: Frequency of data points (h=hourly, D=daily)
    
    Returns:
        DataFrame with synthetic time series data
    """
    logger.info(f"Creating synthetic data: {days} days, frequency={freq}")
    
    # Generate dates
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    dates = pd.date_range(start=start_date, end=end_date, freq=freq)
    
    # Generate synthetic load data with trend and seasonality
    n_points = len(dates)
    
    # Base load with daily and weekly patterns
    t = np.arange(n_points)
    daily_pattern = 50 * np.sin(2 * np.pi * t / 24)  # Daily cycle
    weekly_pattern = 30 * np.sin(2 * np.pi * t / 168)  # Weekly cycle
    trend = 5 * t / n_points  # Linear trend
    noise = np.random.normal(0, 10, n_points)  # Noise
    
    # Combined signal (normalized to reasonable MW values)
    load = 500 + daily_pattern + weekly_pattern + trend + noise
    load = np.maximum(load, 100)  # Ensure positive values
    
    # Create DataFrame
    df = pd.DataFrame({
        'timestamp': dates,
        'ds': dates,  # Prophet expects 'ds' column
        'y': load,   # Prophet expects 'y' column
        'load': load,
    })
    
    logger.info(f"Generated {len(df)} data points from {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    return df


def train_prophet_model(df: pd.DataFrame, horizon: int = 24) -> object:
    """
    Train a Prophet model on the provided data.
    
    Args:
        df: DataFrame with 'ds' and 'y' columns
        horizon: Forecast horizon in hours
    
    Returns:
        Trained Prophet model
    """
    logger.info(f"Training Prophet model with horizon={horizon}")
    
    try:
        from prophet import Prophet
    except ImportError:
        logger.error("Prophet not installed. Install with: pip install prophet")
        raise
    
    # Create and configure Prophet model
    model = Prophet(
        interval_width=0.95,
        seasonality_mode='additive',
        seasonality_prior_scale=10.0,
        changepoint_prior_scale=0.05,
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
    )
    
    # Train model
    logger.info("Fitting Prophet model...")
    import logging as log_module
    # Suppress verbose logging from Prophet
    log_module.getLogger('prophet').setLevel(log_module.WARNING)
    model.fit(df)
    
    logger.info("Model training completed successfully")
    
    return model


def create_test_environment():
    """Create necessary directories and files for test environment."""
    logger.info("Creating test environment directories...")
    
    dirs_to_create = [
        'mlflow_artifacts',
        'logs',
        'tests/fixtures',
        'tests/fixtures/test_data',
    ]
    
    for dir_path in dirs_to_create:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"✓ Created directory: {dir_path}")


def register_model_in_mlflow(model, df: pd.DataFrame, model_id: str, horizon: int = 24):
    """
    Register the trained model in MLflow.
    
    Args:
        model: Trained Prophet model
        df: Training data
        model_id: ID for the model
        horizon: Forecast horizon
    """
    logger.info(f"Registering model in MLflow: {model_id}")
    
    try:
        import mlflow
        from mlflow.models import infer_signature
    except ImportError:
        logger.error("MLflow not installed. Install with: pip install mlflow")
        raise
    
    # Set experiment
    mlflow.set_experiment("test_experiment")
    
    # Start MLflow run
    with mlflow.start_run(run_name=f"test_model_{model_id}"):
        # Log parameters
        mlflow.log_param("model_type", "prophet")
        mlflow.log_param("horizon", horizon)
        mlflow.log_param("freq", "H")
        mlflow.log_param("seasonality_mode", "additive")
        mlflow.log_param("training_days", len(df))
        
        # Log metrics
        mlflow.log_metric("training_samples", len(df))
        
        # Log model
        mlflow.prophet.log_model(
            model,
            "model",
            registered_model_name=model_id,
        )
        
        # Set tags
        mlflow.set_tags({
            "model_type": "prophet",
            "horizon": str(horizon),
            "freq": "H",
            "environment": "test",
            "data_source_config": json.dumps({
                "apis": [
                    {
                        "name": "load",
                        "endpoint": "/api/load",
                        "timeout": 30,
                        "required": True
                    }
                ]
            }),
            "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
            "region": "AKMOLA",
        })
        
        logger.info(f"✓ Model registered in MLflow with run_id: {mlflow.active_run().info.run_id}")
        
        return mlflow.active_run().info.run_id


def save_test_data(df: pd.DataFrame, output_path: str = "tests/fixtures/test_data/sample.csv"):
    """Save test data to file."""
    logger.info(f"Saving test data to {output_path}")
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    
    logger.info(f"✓ Test data saved ({len(df)} rows)")


def create_config_file(horizon: int = 24, output_path: str = "config/test_model_runtime.json"):
    """Create runtime configuration file."""
    logger.info(f"Creating runtime configuration at {output_path}")
    
    config = {
        "environment": "test",
        "model": {
            "type": "prophet",
            "horizon": horizon,
            "freq": "H",
            "seasonality_mode": "additive",
        },
        "data_source": {
            "object_reference": "/KAZ/AKMOLA/@models/P_WATT",
            "apis": [
                {
                    "name": "load",
                    "endpoint": "/api/load",
                    "timeout": 30,
                    "required": True
                }
            ]
        },
        "inference": {
            "timeout": 60,
            "max_workers": 4,
        },
        "created_at": datetime.now().isoformat(),
    }
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    logger.info(f"✓ Configuration file created")


def main():
    """Main setup function."""
    logger.info("=" * 80)
    logger.info("TEST MODEL SETUP - START")
    logger.info("=" * 80)
    
    try:
        # Create test environment
        create_test_environment()
        
        # Create synthetic data
        df = create_synthetic_data(days=30, freq='h')
        
        # Save test data
        save_test_data(df)
        
        # Train Prophet model
        model = train_prophet_model(df, horizon=24)
        
        # Register model in MLflow
        run_id = register_model_in_mlflow(
            model,
            df,
            model_id="prophet_watt_h_AKMOLA_test",
            horizon=24
        )
        
        # Create configuration
        create_config_file(horizon=24)
        
        logger.info("=" * 80)
        logger.info("✅ TEST MODEL SETUP - COMPLETE")
        logger.info("=" * 80)
        logger.info(f"\nModel registered with run_id: {run_id}")
        logger.info(f"Model ID: prophet_watt_h_AKMOLA_test")
        logger.info(f"Horizon: 24 hours")
        logger.info(f"\nNext steps:")
        logger.info(f"1. Start the API: python -m uvicorn src.api.main:app --reload")
        logger.info(f"2. Test prediction: curl -X POST http://localhost:8000/predict -H 'Content-Type: application/json' -d '{{\"object_reference\": \"/KAZ/AKMOLA/@models/P_WATT\", \"model_id\": \"prophet_watt_h_AKMOLA_test\"}}'")
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
