# Mariya Polkovnikova
# 2026.03.12, 11:21 AM


from typing import Any, Optional, List
from enum import StrEnum

from fastapi import status
from fastapi.responses import JSONResponse


class State(StrEnum):
    START = "start"
    PROCESSING = "processing"
    DONE = "done"


class HTTPMessages:
    SC200 = status.HTTP_200_OK
    SC201 = status.HTTP_201_CREATED
    SC204 = status.HTTP_204_NO_CONTENT
    SC202 = status.HTTP_202_ACCEPTED
    SC404 = status.HTTP_404_NOT_FOUND
    SC422 = status.HTTP_422_UNPROCESSABLE_ENTITY
    SC500 = status.HTTP_500_INTERNAL_SERVER_ERROR
    SC503 = status.HTTP_503_SERVICE_UNAVAILABLE

    @staticmethod
    def response(status_code: int, message: Optional[str] = None) -> dict[str, Any]:
        output = {"status": status_code}
        if message:
            output["message"] = message
        return output

    @staticmethod
    def message503(mode: str) -> str:
        return f"{mode} is not available, so it is impossible to take values ​​at this time."

    def to_json_response(self, id: str, data: dict) -> JSONResponse:
        status_code = data.get("status", 0)
        data["task_id"] = id
        return JSONResponse(content=data, status_code=status_code)

    # 200
    @classmethod
    def ok_done(cls, data: Any, is_dict: bool = False) -> JSONResponse:
        content = cls.response(cls.SC200)
        content["state"] = State.DONE
        content["data"] = data
        if is_dict: return content
        return JSONResponse(content=content, status_code=cls.SC200)

    # 202
    @classmethod
    def accepted_start(cls, id: str, is_dict: bool = False) -> JSONResponse:
        content = cls.response(cls.SC202)
        content["task_id"] = id
        content["state"] = State.START
        if is_dict: return content
        return JSONResponse(content=content, status_code=cls.SC202)

    @classmethod
    def accepted_processing(cls, id: str, is_dict: bool = False) -> JSONResponse:
        content = cls.response(cls.SC202)
        content["task_id"] = id
        content["state"] = State.PROCESSING
        if is_dict: return content
        return JSONResponse(content=content, status_code=cls.SC202)

    # 404
    @classmethod
    def not_found(cls, is_dict: bool = False) -> JSONResponse:
        content = cls.response(cls.SC404, "API not found")
        if is_dict: return content
        return JSONResponse(content=content, status_code=cls.SC404)

    # 422
    @classmethod
    def unprocessable_entity(cls, errors: List[str], is_dict: bool = False) -> JSONResponse:
        content = cls.response(cls.SC422, "A valid JSON format was expected, but the data was not received or was invalid.")
        content["details"] = errors
        if is_dict: return content
        return JSONResponse(content=content, status_code=cls.SC422)

    @classmethod
    def unprocessable_entity_ndc(cls, is_dict: bool = False) -> JSONResponse:
        content = cls.response(cls.SC422, "Invalid format of input data set sent from NDC archives.")
        if is_dict: return content
        return JSONResponse(content=content, status_code=cls.SC422)

    @classmethod
    def unprocessable_entity_forecast(cls, msg: str, is_dict: bool = False) -> JSONResponse:
        content = cls.response(cls.SC422, f"Forecast execution error: {msg}")
        if is_dict: return content
        return JSONResponse(content=content, status_code=cls.SC422)

    # 500
    @classmethod
    def internal_server_error(cls, msg: str, is_dict: bool = False) -> JSONResponse:
        content = cls.response(cls.SC500, f"Internal server error: {msg}")
        if is_dict: return content
        return JSONResponse(content=content, status_code=cls.SC500)

    # 503
    @classmethod
    def service_unavailable_ndc(cls, mode: str, msg: str = "", is_dict: bool = False) -> JSONResponse:
        content = cls.response(cls.SC503, cls.message503("NDC"))
        if msg: content["message"] += f" Error: {msg}"
        if is_dict: return content
        return JSONResponse(content=content, status_code=cls.SC503)

    @classmethod
    def service_unavailable_rz(cls, msg: str = "", is_dict: bool = False) -> JSONResponse:
        content = cls.response(cls.SC503, cls.message503("RZ"))
        if msg: content["message"] += f" Error: {msg}"
        if is_dict: return content
        return JSONResponse(content=content, status_code=cls.SC503)
