from os import getenv
from pathlib import Path


_default_redis_host = "redis" if Path("/.dockerenv").exists() else "127.0.0.1"

REDIS_URL = getenv("REDIS_URL", f"redis://{_default_redis_host}:6379/0")
REDIS_TIMEOUT = int(getenv("REDIS_TIMEOUT", "3600"))

_historical_urls = getenv("HISTORICAL_DATA_URLS") or getenv("HISTORICAL_DATA_URL") or getenv("SCADA_URL")
if _historical_urls:
    HISTORICAL_DATA_URLS = [item.strip() for item in _historical_urls.split(",") if item.strip()]
else:
    HISTORICAL_DATA_URLS = ["http://127.0.0.1:7080/api/v1/read/archives"]

CMMS_URL = getenv("CMMS_URL") or getenv("CMMS_API_URL") or "http://localhost:8000/api/v1/cmms"
RZ_URL = getenv("RZ_URL") or CMMS_URL
WEATHER_URL = getenv("WEATHER_URL") or getenv("WEATHER_API_URL") or ""

HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json",
}

CLIENT_TIMEOUT_ONE = int(getenv("CLIENT_TIMEOUT_ONE", "30"))
CLIENT_TIMEOUT_ALL = int(getenv("CLIENT_TIMEOUT_ALL", "120"))

GMT_TO_ASTANA_HOURS = int(getenv("GMT_TO_ASTANA_HOURS", "5"))

TAG_PREDICT_CREATE = "predict_create"
TAG_PREDICT_UPDATE = "predict_update"