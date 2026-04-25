# Mariya Polkovnikova
# 2026.03.15, 02:46 PM


from os import getenv


# -- Redis ---

REDIS_URL = "redis://redis:6379/0"
REDIS_TIMEOUT = 3600  # 1 hour


# -- Historical Data / NDC ---

HISTORICAL_DATA_HOSTS = ["10.210.1.11", "10.210.1.13", "10.210.1.15"]
HISTORICAL_DATA_URLS = [f"http://{host}:7080/api/read/archive" for host in HISTORICAL_DATA_HOSTS]


# --- Repairs / CMMS ---

CMMS_URL = getenv("CMMS_URL") or getenv("CMMS_API_URL")
RZ_URL = CMMS_URL


# --- General ---

HEADERS = {"Content-Type": "application/json"}

CLIENT_TIMEOUT_ONE = 30
CLIENT_TIMEOUT_ALL = CLIENT_TIMEOUT_ONE * 5

GMT_TO_ASTANA_HOURS = 5


# --- Tag ---

TAG_PREDICT_CREATE = "predict_create"
TAG_PREDICT_UPDATE = "predict_update"
