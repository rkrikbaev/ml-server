#
# 2026.03.11, 10:53 AM


from typing import Any, Dict

from taskiq_redis import RedisStreamBroker, RedisAsyncResultBackend

from api.message import HTTPMessages
from api.inference import predict

from .archives import get_data_from_arvhives
from .model import get_model
from .rz import get_rz_data
from .evaluation import count_input_qds, evaluate_input_quality
from .result import get_api_predict

from api.config import REDIS_URL

from os import getenv
# from dotenv import load_dotenv

# load_dotenv()

result_backend = RedisAsyncResultBackend(REDIS_URL, result_ex_time=60)
broker = RedisStreamBroker(REDIS_URL).with_result_backend(result_backend)


@broker.task
async def api_predict(data: Dict[str, Any]) -> Dict[str, Any]:
    # NDC
    output = await get_data_from_arvhives(data["mode"], data["archives"], data["step"], data["online"])
    if isinstance(output, dict): return output

    # Get: timestamp, value, qds
    timestamp, value, qds = output[0], output[1], output[2]
    del output

    # Model Initialization
    model = get_model(data["model_path"], data["step"], data["use_dynamic_normalization"])

    # RZ
    mes = data["model_path"].split("/")[3] if data["model_path"] else None

    df_rz = await get_rz_data(getenv("RZ_API_URL"), model, mes, timestamp[0], data["step"], data["output_range"])
    if isinstance(df_rz, dict): return df_rz

    # Primary
    try:
        preds, pred_ts, is_matching = predict(
            y=value,
            timestamps=timestamp,
            model=model,
            step=data["step"],
            output_range=data["output_range"],
            online=data["online"],
            df_rz_melt=df_rz
        )
    except Exception as e:  # 422
        return HTTPMessages.unprocessable_entity_forecast(str(e), is_dict=True)

    # QDS Assessment
    critical_freq, non_critical_freq = count_input_qds(timestamp, value, qds)
    input_qds, input_reason = evaluate_input_quality(critical_freq, non_critical_freq)

    return HTTPMessages.ok_done(
        get_api_predict(
            model,
            is_matching,
            input_qds,
            input_reason,
            data["clip_negatives_to_0"],
            preds,
            pred_ts
        ),
        is_dict=True
    )
