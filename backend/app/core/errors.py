"""Public errors always contain a string detail, never submitted secret values."""

import sqlite3

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "请求未能完成"
        return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Do not echo exc.errors(): Pydantic includes raw input in those objects.
        return JSONResponse(
            {"detail": "请求参数不符合接口约定，请检查字段、类型和长度"}, status_code=422
        )

    @app.exception_handler(sqlite3.IntegrityError)
    async def integrity_error(request: Request, exc: sqlite3.IntegrityError):
        return JSONResponse({"detail": "数据冲突或引用无效"}, status_code=409)

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request: Request, exc: sqlite3.OperationalError):
        return JSONResponse({"detail": "数据库暂不可用，请稍后重试"}, status_code=503)

    @app.exception_handler(ResponseValidationError)
    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return JSONResponse({"detail": "服务内部错误"}, status_code=500)
