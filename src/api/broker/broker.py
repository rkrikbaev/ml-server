# Mariya Polkovnikova
# 2026.03.11, 10:53 AM


from typing import Any, Dict
from os import getenv

# Use Redis result storage whenever it is available so the two-step
# /predict polling flow can work in Docker/test environments as well.
TEST_MODE = getenv("TEST_MODE", "false").lower() == "true"
USE_IN_MEMORY_BROKER = getenv("USE_IN_MEMORY_BROKER", "false").lower() == "true"

if not USE_IN_MEMORY_BROKER:
    from taskiq_redis import RedisStreamBroker, RedisAsyncResultBackend
    from api import REDIS_URL, REDIS_TIMEOUT
    result_backend = RedisAsyncResultBackend(REDIS_URL, result_ex_time=REDIS_TIMEOUT)
    broker = RedisStreamBroker(REDIS_URL).with_result_backend(result_backend)
elif TEST_MODE:
    from taskiq import InMemoryBroker
    from taskiq.result_backends.dummy import DummyResultBackend

    result_backend = DummyResultBackend()
    broker = InMemoryBroker().with_result_backend(result_backend)
else:
    from taskiq_redis import RedisStreamBroker, RedisAsyncResultBackend
    from api import REDIS_URL, REDIS_TIMEOUT

    result_backend = RedisAsyncResultBackend(REDIS_URL, result_ex_time=REDIS_TIMEOUT)
    broker = RedisStreamBroker(REDIS_URL).with_result_backend(result_backend)

from .tasks import predict_logic


@broker.task
async def api_predict(data: Dict[str, Any]) -> Dict[str, Any]:
    output = await predict_logic(
        model_id=data["model_id"],
        online=data["online"],
        selector=data.get("selector"),
    )
    output["object_reference"] = data["object_reference"]
    return output


# async def hash_task_ids(task_id: str) -> None:
#     async with Redis(connection_pool=self.redis_pool) as redis:
#         if self.result_ex_time:
#             await redis.set(name=name, value=value, ex=self.result_ex_time)
