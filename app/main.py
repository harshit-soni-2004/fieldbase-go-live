from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api.audit import AuditMiddleware
from app.api.auth import validate_environment_security
from app.api.contracts import router as contracts_router
from app.api.problems import ProblemException, problem_exception_handler, problem_response
from app.api.tenants import router as tenants_router
from app.db import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_environment_security()
    init_db()
    yield

app = FastAPI(title="Go-live Admin API", lifespan=lifespan)

app.add_middleware(AuditMiddleware)

app.add_exception_handler(ProblemException, problem_exception_handler)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return problem_response(
        status=422,
        code="VALIDATION_ERROR",
        title="Validation error",
        detail=str(exc),
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return problem_response(
        status=exc.status_code,
        code="HTTP_ERROR",
        title="HTTP Error",
        detail=str(exc.detail),
    )

app.include_router(contracts_router)
app.include_router(tenants_router)
