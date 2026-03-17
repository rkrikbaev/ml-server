#
# 2026.03.11, 10:53 AM


from typing import Any, Dict

from taskiq_redis import RedisStreamBroker, RedisAsyncResultBackend

from api import REDIS_URL, REDIS_TIMEOUT
from .tasks import predict_logic

result_backend = RedisAsyncResultBackend(REDIS_URL, result_ex_time=REDIS_TIMEOUT)
broker = RedisStreamBroker(REDIS_URL).with_result_backend(result_backend)


@broker.task
async def api_predict(data: Dict[str, Any]) -> Dict[str, Any]:
    return await predict_logic(
        mode=data["mode"],
        model_path=data["model_path"],
        archives=data["archives"],
        step=data["step"],
        output_range=data["output_range"],
        online=data["online"],
        clip_negatives_to_0=data["clip_negatives_to_0"],
        use_dynamic_normalization=data["use_dynamic_normalization"]
    )
