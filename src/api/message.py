# Mariya Polkovnikova
# 2026.03.12, 11:21 AM


from typing import List, Dict, Any, Optional
from enum import IntEnum, StrEnum

from fastapi import status
from fastapi.responses import JSONResponse


class HTTPState(StrEnum):
    START = "start"
    PROCESSING = "processing"
    DONE = "done"

    @classmethod
    def state_start(cls, content: Dict[str, Any]) -> Dict[str, Any]:
        content["state"] = cls.START
        return content

    @classmethod
    def state_processing(cls, content: Dict[str, Any]) -> Dict[str, Any]:
        content["state"] = cls.PROCESSING
        return content

    @classmethod
    def state_done(cls, content: Dict[str, Any]) -> Dict[str, Any]:
        content["state"] = cls.DONE
        return content


class HTTPStatuses(IntEnum):
    SC200 = status.HTTP_200_OK
    SC202 = status.HTTP_202_ACCEPTED
    SC404 = status.HTTP_404_NOT_FOUND
    SC422 = status.HTTP_422_UNPROCESSABLE_ENTITY
    SC500 = status.HTTP_500_INTERNAL_SERVER_ERROR
    SC503 = status.HTTP_503_SERVICE_UNAVAILABLE


class HTTPMessages:
    @staticmethod
    def response(status_code: int, message: Optional[str] = None) -> dict[str, Any]:
        output = {"status": status_code}
        if message:
            output["message"] = message
        return output

    @staticmethod
    def message503(mode: str) -> str:
        return f"{mode} is not available, so it is impossible to take values ​​at this time."

    def to_json_response(self, data: dict, id: Optional[str] = None, state: str = "") -> JSONResponse:
        if not isinstance(data, dict):
            return JSONResponse(
                content=self.response(
                    HTTPStatuses.SC500,
                    "Invalid response format: expected a dictionary."
                ),
                status_code=HTTPStatuses.SC500
            )

        status_code = data.get("status", 0)

        if id:
            data["task_id"] = id

        match state:
            case HTTPState.START:
                HTTPState.state_start(data)
            case HTTPState.PROCESSING:
                HTTPState.state_processing(data)
            case HTTPState.DONE:
                HTTPState.state_done(data)
            case _:
                pass

        return JSONResponse(content=data, status_code=status_code)

    # 200
    @classmethod
    def ok_done(cls, data: Any) -> JSONResponse:
        content = cls.response(HTTPStatuses.SC200)
        content["data"] = data
        return content

    # 202
    @classmethod
    def accepted_start(cls, id: str, fp_path: str) -> JSONResponse:
        content = cls.response(HTTPStatuses.SC202)
        content["task_id"] = id
        content["object_reference"] = fp_path
        return content

    @classmethod
    def accepted_processing(cls, id: str) -> JSONResponse:
        content = cls.response(HTTPStatuses.SC202)
        content["task_id"] = id
        return content

    # 404
    @classmethod
    def not_found(cls) -> JSONResponse:
        content = cls.response(HTTPStatuses.SC404, "API not found")
        return content

    # 422
    @classmethod
    def unprocessable_entity(cls, errors: Dict[str, List[str]]) -> JSONResponse:
        content = cls.response(HTTPStatuses.SC422, "A valid JSON format was expected, but the data was not received or was invalid.")
        content["details"] = errors
        return content

    @classmethod
    def unprocessable_entity_ndc(cls, quality: int) -> JSONResponse:
        content = cls.response(HTTPStatuses.SC422, "Incorrect data in the dataset from archives.")
        content["quality"] = quality
        return content

    @classmethod
    def unprocessable_entity_forecast(cls, msg: str) -> JSONResponse:
        content = cls.response(HTTPStatuses.SC422, f"Forecast execution error: {msg}")
        return content

    @classmethod
    def unprocessable_entity_weather(cls, msg: str = "") -> JSONResponse:
        content = cls.response(HTTPStatuses.SC422, "Incorrect data in the dataset from weather service.")
        if msg:
            content["details"] = msg
        return content

    @classmethod
    def unprocessable_entity_historical_data(cls, msg: str = "") -> JSONResponse:
        content = cls.response(HTTPStatuses.SC422, "Incorrect data in the dataset from HISTORICAL_DATA.")
        if msg:
            content["details"] = msg
        return content

    @classmethod
    def model_config_not_found(cls, model_id: str) -> JSONResponse:
        content = cls.response(HTTPStatuses.SC422, f"Model launch aborted: config.json not found for model '{model_id}'.")
        return content

    @classmethod
    def model_launch_aborted_no_data(cls) -> JSONResponse:
        content = cls.response(HTTPStatuses.SC422, "Model launch aborted: no input data received from archives.")
        return content

    # 500
    @classmethod
    def internal_server_error(cls, msg: str) -> JSONResponse:
        content = cls.response(HTTPStatuses.SC500, f"Internal server error: {msg}")
        return content

    # 503
    @classmethod
    def service_unavailable_ndc(cls, msg: str = "") -> JSONResponse:
        content = cls.response(HTTPStatuses.SC503, cls.message503("NDC"))
        if msg: content["message"] += f" Error: {msg}"
        return content

    @classmethod
    def service_unavailable_rz(cls, msg: str = "") -> JSONResponse:
        content = cls.response(HTTPStatuses.SC503, cls.message503("RZ"))
        if msg: content["message"] += f" Error: {msg}"
        return content

    @classmethod
    def service_unavailable_weather(cls, msg: str = "") -> JSONResponse:
        content = cls.response(HTTPStatuses.SC503, cls.message503("WEATHER"))
        if msg: content["message"] += f" Error: {msg}"
        return content

    @classmethod
    def service_unavailable_historical_data(cls, msg: str = "") -> JSONResponse:
        content = cls.response(HTTPStatuses.SC503, cls.message503("HISTORICAL_DATA"))
        if msg: content["message"] += f" Error: {msg}"
        return content
