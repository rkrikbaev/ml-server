# Mariya Polkovnikova
# 2026.03.15, 02:46 PM



REDIS_URL = "redis://redis:6379/0"
# REDIS_URL = "redis://localhost:6379/0"
REDIS_TIMEOUT = 3600  # 1 hour

NDC_HOSTS = ["192.168.50.141"]
# NDC_HOSTS = ["10.210.1.11", "10.210.1.13", "10.210.1.15"]
NDC_URLS = [f"http://{host}:7080/api/read/archive" for host in NDC_HOSTS]

HEADERS = {"Content-Type": "application/json"}
TIMEOUT = 30
