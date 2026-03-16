# Mariya Polkovnikova
# 2026.03.13, 09:45 AM


from typing import List, Tuple, Dict, Any, Optional, Callable
from json import dumps

from httpx import AsyncClient
from fastapi.responses import JSONResponse

from api import HTTPMessages, QDS, generate_timestamp, interpolate_nan_1d
from api.config import NDC_URLS, HEADERS, TIMEOUT

import numpy as np


async def send_ndc_url(
    data: str,
    online: bool,
    func: Callable[[dict[str, Any], bool], Tuple[np.ndarray]]
) -> JSONResponse | Tuple[List[int | Optional[float]]]:
    """
    Sends a POST request to the NDC archives API with the provided data.

    :param str data: The data to be sent in the request body.
    :param bool online: Whether the request is for online data.
    :param Callable[[int, dict[Any], dict[Any]], dict[Any]] func: The function
        to be called with the response data.

    :return: The response from the NDC archives API, or an error message if
        the request fails.
    :rtype: JSONResponse | Tuple[List[int | Optional[float]]]
    """

    output = None

    async with AsyncClient(timeout=TIMEOUT * 5) as client:
        request_success = False
        is_error = None

        for url in NDC_URLS:
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
                        output = func(response, online)

                    request_success = True
                    break

                else:
                    continue

            except Exception as e:
                is_error = str(e)
                continue

        if not request_success:  # 503
            return HTTPMessages.service_unavailable_ndc(is_error, is_dict=True)

    if output is None:  # 503
        return HTTPMessages.unprocessable_entity_ndc(is_dict=True)

    return output


def extract_data(values: List, interpolate: bool) -> Tuple[np.ndarray]:
    """
    Extracts timestamps, values, and quality descriptors from a list of
    values.

    :param List values: A list of tuples containing timestamps, values, and
        quality descriptors.
    :param bool interpolate: Whether to interpolate missing values in the
        values array.

    :return: A tuple containing arrays of timestamps, values, and quality
        descriptors.
    :rtype: Tuple[np.ndarray]
    """

    # Get timestamps
    timestamps = np.array([ts for ts, _, _ in values], dtype=int)

    # Get QDS
    qds = np.array([QDS.MISSING_VALUE if qds is None else qds for _, _, qds in values], dtype=int)

    # Get y
    y = np.array([val for _, val, _ in values], dtype=float)

    # Interpolate nan values in y
    if interpolate:
        y = interpolate_nan_1d(y)

    return timestamps, y, qds


async def get_data_from_arvhives(mode: str, archives: List[str], step: int, online: bool):
    def func(data: Dict[str, Any], online: bool) -> JSONResponse | Tuple[List[int | Optional[float]]]:
        """
        Extracts data from the NDC archives response.

        :param Dict[str, Any] data: The response data from the NDC archives
            API.
        :param bool online: Whether the request is for online data.

        :return: A tuple containing lists of timestamps, values, and quality
            descriptors.
        :rtype: JSONResponse | Tuple[List[int | Optional[float]]]
        """

        timestamps, values, qds = [], [], []

        try:
            for item in data.values():
                ts, yv, qv = extract_data(item, interpolate=not online)
                timestamps.append(ts)
                values.append(yv)
                qds.append(qv)

        except Exception:  # 422
            return HTTPMessages.unprocessable_entity_ndc(is_dict=True)

        return timestamps, values, qds

    from_tp, to_tp = generate_timestamp(mode)
    data = {
        "from": from_tp,
        "to": to_tp,
        "archive": archives,
        "step": step // 1000
    }
    return await send_ndc_url(dumps(data), online, func)  # 200, 422, 503
