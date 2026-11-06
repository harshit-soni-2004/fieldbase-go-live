import os
from typing import Callable, Optional
from fastapi import Header
from app.api.problems import ProblemException

def get_env_tokens() -> tuple[str, str, str]:
    app_env = os.environ.get("APP_ENV", "local")
    agent_token = os.environ.get("AGENT_TOKEN", "agent-local")
    operator_token = os.environ.get("OPERATOR_TOKEN", "operator-local")
    return app_env, agent_token, operator_token

def validate_environment_security() -> None:
    app_env, agent_token, operator_token = get_env_tokens()
    if app_env != "local":
        if agent_token == "agent-local" or operator_token == "operator-local":
            raise RuntimeError(
                f"Refusing to start in APP_ENV={app_env} with default local tokens set."
            )

def get_current_actor(authorization: Optional[str] = Header(None)) -> str:
    validate_environment_security()
    if not authorization or not authorization.startswith("Bearer "):
        raise ProblemException(
            status=401,
            code="UNAUTHORIZED",
            title="Unauthorized",
            detail="Missing or invalid bearer token",
        )
    
    token = authorization[len("Bearer "):].strip()
    _, agent_token, operator_token = get_env_tokens()

    if token == agent_token:
        return "agent"
    elif token == operator_token:
        return "operator"
    else:
        raise ProblemException(
            status=401,
            code="UNAUTHORIZED",
            title="Unauthorized",
            detail="Unknown bearer token",
        )

def require_role(allowed_roles: list[str]) -> Callable[[str], str]:
    def dependency(actor: str = Header(..., alias="Authorization")) -> str:
        # Note: in FastAPI dependencies, we compose with get_current_actor
        raise NotImplementedError("Use require_roles dependency wrapper")
    return dependency

class RoleChecker:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, actor: str = None) -> str:
        # We will use this with Depends(get_current_actor)
        if actor not in self.allowed_roles:
            if actor == "agent":
                raise ProblemException(
                    status=403,
                    code="AGENT_FORBIDDEN",
                    title="Agent forbidden",
                    detail="Agent role is not permitted to perform this action",
                )
            raise ProblemException(
                status=403,
                code="FORBIDDEN",
                title="Forbidden",
                detail="Action not permitted for current role",
            )
        return actor

