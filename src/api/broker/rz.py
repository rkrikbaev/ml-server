# Mariya Polkovnikova
# 2026.03.16, 08:58 AM


from typing import Dict, Any, Optional, Callable
from json import dumps

from httpx import AsyncClient
from fastapi.responses import JSONResponse

from fpforecast.constants import KOD_OBLASTI_TO_PATH
from fpforecast.features import melt_rz_data
from fpforecast.models.ar import ModelWithMetaInfoAr

from api.message import HTTPMessages
from api.inference import get_pred_timestamps
from api.config import HEADERS, TIMEOUT

import pandas as pd


async def send_rz_url(
    url: str,
    data: str,
    func: Callable[[Dict[str, Any]], pd.DataFrame]
) -> JSONResponse | pd.DataFrame:
    """
    Send a POST request to the specified URL with the given data.

    :param str url: The URL to send the request to.
    :param str data: The JSON-formatted data to send in the request body.
    :param Callable[[Dict[str, Any]], pd.DataFrame] func: A function to
        process the response JSON.

    :return: The processed output or an error message.
    :rtype: JSONResponse | pd.DataFrame
    """

    output = None

    async with AsyncClient(timeout=TIMEOUT * 5) as client:
        request_success = False
        is_error = None

        try:
            request = await client.post(
                url=url,
                headers=HEADERS,
                data=data,
                timeout=TIMEOUT
            )
            if 200 <= request.status_code < 300:
                response = request.json()
                if response:
                    output = func(response)

                request_success = True

        except Exception as e:
            is_error = str(e)

        if not request_success:  # 503
            return HTTPMessages.service_unavailable_rz(is_error, is_dict=True)

    if output is None:  # 503
        return HTTPMessages.service_unavailable_rz(is_dict=True)

    return output


def convert_rz_format(data: Dict[str, Any]) -> pd.DataFrame:
    """
    Convert RZ data format to pandas DataFrame.

    :param Dict[str, Any] data: RZ data in original format.

    :return: RZ data in melted format.
    :rtype: pandas.DataFrame
    """

    data_flat = []
    for item in data:
        for id_, values_outer in item.items():
            for i, values in enumerate(values_outer):
                data_flat.append(values | {"id": id_, "index": i})

    df = pd.DataFrame(data_flat)

    df["data_N"] = df["start_actual"].fillna(df["start_approved"]).fillna(df["start_requested"])
    df["data_K"] = df["end_actual"].fillna(df["end_approved"]).fillna(df["end_requested"])
    df["cod_en_obj"] = df["id"].str[:4]
    df["cod_en_obj_vidobor"] = df["id"].str[:6]
    df["occurence"] = 1
    df["area_code"] = df["area_code"]
    df["region_path"] = df["area_code"].fillna(-1).astype(int).map(KOD_OBLASTI_TO_PATH)
    df["mes"] = df["region_path"].str.split("/").str[1]

    # Convert from timestamp in ms to datetime
    df["date_post"] = pd.to_datetime(df["date_post"], unit="ms")
    df["data_N"] = pd.to_datetime(df["data_N"], unit="ms")
    df["data_K"] = pd.to_datetime(df["data_K"], unit="ms")

    df = df.rename(columns={
        "date_post": "data_post",
        "id": "shifrIMJ",
        "object_type_code": "Kod_TypObj",
        "p_descent": "p_sni",
    })
    cols_to_check = [
        "data_post",
        "shifrIMJ",
        "cod_en_obj",
        "cod_en_obj_vidobor",
        "mes",
        "region_path",
        "Kod_TypObj",
        "occurence",
        "p_sni",
        "data_N",
        "data_K"
    ]
    assert all(col in df.columns for col in cols_to_check), set(cols_to_check) - set(df.columns)

    df = df[cols_to_check]
    df = df.dropna(subset=cols_to_check)
    df["shifrIMJ"] = df["shifrIMJ"].astype(str)
    df["cod_en_obj"] = df["cod_en_obj"].astype(str)
    df["cod_en_obj_vidobor"] = df["cod_en_obj_vidobor"].astype(str)
    df["mes"] = df["mes"].astype(str)
    df["region_path"] = df["region_path"].astype(str)

    df_melt = melt_rz_data(df)
    return df_melt


def require_rz_data(model: Any) -> bool:
    """
    Check if RZ data is required for the model.

    :param Any model: Model object.

    :return: True if RZ data is required, False otherwise.
    :rtype: bool
    """

    if not isinstance(model, ModelWithMetaInfoAr):
        return False

    if model.features_info is None:
        return False

    if any(
        feature_info.name.startswith(("is_repair_", "repair_power_drop_"))
        for feature_info in model.features_info
    ):
        return True

    return False


async def get_rz_data(
    url: str,
    model: Any,
    mes: Optional[str],
    timestamp: list[Any],
    step: int,
    period: int
) -> Optional[JSONResponse | pd.DataFrame]:
    """
    Get RZ data for the specified model and timestamps.

    :param str url: The URL to send the request to.
    :param Any model: Model object.
    :param Optional[str] mes: Optional mesh code.
    :param list[Any] timestamp: List of timestamps.
    :param int step: Step size.
    :param int period: Output range period.

    :return: RZ data or an error message.
    :rtype: Optional[JSONResponse | pd.DataFrame]
    """

    is_rz = require_rz_data(model)
    if url is not None and is_rz:
        try:
            _, pred_timestamps = get_pred_timestamps(timestamp, step, period)
            start_data = int(pred_timestamps[0])
            end_data = int(pred_timestamps[-1])

            return await send_rz_url(  # 200, 503
                url,
                dumps({
                    "mes": mes,
                    "start_data": start_data,
                    "end_data": end_data
                }),
                convert_rz_format
            )

        except Exception as e:  # 500
            return HTTPMessages.internal_server_error(str(e), is_dict=True)
