# Integrating the MLflow Registry into ML-Server

1. Architectural Role
MLflow: Certificate Storage, Model Registry (PostgreSQL), and Metadata Sources.
ML-Server: Loads the model and configures the cache from MLflow upon client request, using the model_id and alias/version.

2. Artifact Structure (Convention)
Each training run requires saving the data to a single directory: package/:
text
bundle/
├── model/ # MLmodel and model binary file
├── configuration/
│ └── cache_config.json # Caching parameters, thresholds, metadata
└── assets/ # Additional files (preprocessing, dictionaries)

3. Training Phase (Harvesting)
The model developer should use the log_bundle method:
Save the model using mlflow.<flavor>.log_model(..., artifact_path="bundle/model").
Save the JSON config using mlflow.log_dict(config_dict, "bundle/config/cache_config.json").
Register the model: mlflow.register_model(model_uri=..., name=model_id).

4. Serving Phase (Output Side: ML Server)
Implement the ModelProvider in the ml-server module.

Workflow:
Receiving a request: The server receives the model_id and selector (version or alias, such as prod).
Cache check: If (model_id, selector) are already loaded and up-to-date in local memory/disk, use them.

MLflow API Request (MLflowClient) from ML-Server:

```python
# Get metadata version
version_info = client.get_model_version_by_alias(model_id, selector)
run_id = version_info.run_id

# Download the entire bundle
local_path = client.download_artifacts(run_id, "bundle")
```

Initialization:

Download cache_config.json to configure the service logic.
Download weight models from the /model subfolder.
Hot swap: replace the old in-memory model version with the new server without downtime.

5. API Contract (Example)
The user sends a request to your MLflow server:
```JSON
    {
    "model_selection": {
    "model_id": "user_scoring_v2",
    "version_alias": "champion"
    },
    }
```

6. Developer Checklist:
Implement the sync_with_registry(model_id, selector) method.
Implement a mechanism for clearing old models from disk (LRU Cache) to prevent the server database from becoming overloaded.
Add error handling: if MLflow is unavailable, the server should run on the latest, more loaded version (fallback).