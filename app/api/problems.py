from typing import Any, Optional
from fastapi import Request
from fastapi.responses import JSONResponse

class ProblemException(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str,
        headers: Optional[dict[str, str]] = None,
    ):
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.headers = headers or {}
        super().__init__(detail)

def problem_response(
    status: int,
    code: str,
    title: str,
    detail: str,
    headers: Optional[dict[str, str]] = None,
) -> JSONResponse:
    content = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
    }
    all_headers = {"Content-Type": "application/problem+json"}
    if headers:
        all_headers.update(headers)
    return JSONResponse(status_code=status, content=content, headers=all_headers)

async def problem_exception_handler(request: Request, exc: ProblemException) -> JSONResponse:
    return problem_response(
        status=exc.status,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        headers=exc.headers,
    )
