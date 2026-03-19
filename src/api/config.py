# Mariya Polkovnikova
# 2026.03.15, 02:46 PM


from os import getenv


# -- Redis ---

REDIS_URL = "redis://redis:6379/0"
REDIS_TIMEOUT = 3600  # 1 hour


# -- NDC ---

NDC_HOSTS = ["10.210.1.11", "10.210.1.13", "10.210.1.15"]
NDC_URLS = [f"http://{host}:7080/api/read/archive" for host in NDC_HOSTS]


# --- RZ ---

RZ_URL = getenv("RZ_API_URL")


# --- General ---

HEADERS = {"Content-Type": "application/json"}

CLIENT_TIMEOUT_ONE = 30
CLIENT_TIMEOUT_ALL = CLIENT_TIMEOUT_ONE * 5

GMT_TO_ASTANA_HOURS = 5


# --- Tag ---

TAG_PREDICT_CREATE = "predict_create"
TAG_PREDICT_UPDATE = "predict_update"
