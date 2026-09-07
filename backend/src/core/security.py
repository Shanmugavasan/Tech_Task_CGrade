import os
import json
import hmac
import secrets
import time
import base64
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, WebSocket
from pydantic import BaseModel


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    role: str
    handler_types: frozenset[str]


class LoginRequest(BaseModel):
    username: str
    password: str


_current_user: ContextVar[AuthenticatedUser | None] = ContextVar("current_user", default=None)
_sessions: dict[str, tuple[AuthenticatedUser, float]] = {}

DEFAULT_USERS = {
    "claims.handler": {"password": "claims-demo", "role": "handler", "handler_types": ["Claims"]},
    "home.handler": {"password": "home-demo", "role": "handler", "handler_types": ["Home"]},
    "motor.handler": {"password": "motor-demo", "role": "handler", "handler_types": ["Motor"]},
    "operations.supervisor": {"password": "supervisor-demo", "role": "supervisor", "handler_types": ["Claims", "Home", "Motor", "Liability", "Finance"]},
    "audit.user": {"password": "audit-demo", "role": "auditor", "handler_types": ["Claims", "Home", "Motor", "Liability", "Finance"]},
}
SESSION_COOKIE = "triage_session"
SESSION_TTL_SECONDS = 8 * 60 * 60


def _session_secret() -> bytes:
    return os.getenv("SESSION_SECRET", os.getenv("AUTH_TOKEN", "local-development-session-secret")).encode()


def _encode_session(user: AuthenticatedUser) -> str:
    payload = json.dumps({
        "user_id": user.user_id,
        "role": user.role,
        "handler_types": sorted(user.handler_types),
        "expires_at": int(time.time()) + SESSION_TTL_SECONDS,
    }, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(_session_secret(), encoded.encode(), "sha256").hexdigest()
    return f"{encoded}.{signature}"


def _decode_session(value: str) -> AuthenticatedUser | None:
    try:
        encoded, signature = value.rsplit(".", 1)
        expected = hmac.new(_session_secret(), encoded.encode(), "sha256").hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if int(payload["expires_at"]) <= int(time.time()):
            return None
        return AuthenticatedUser(
            payload["user_id"], payload["role"], frozenset(payload["handler_types"])
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _user_for_username(username: str) -> AuthenticatedUser | None:
    users = DEFAULT_USERS.copy()
    configured = os.getenv("AUTH_USERS_JSON")
    if configured:
        records = json.loads(configured)
        users = {
            record.get("username", record.get("user_id")): record
            for record in records
        }
    record = users.get(username)
    if not record:
        return None
    return AuthenticatedUser(username, record["role"], frozenset(record.get("handler_types", [])))


def _password_for_username(username: str) -> str | None:
    configured = os.getenv("AUTH_USERS_JSON")
    users = DEFAULT_USERS
    if configured:
        records = json.loads(configured)
        users = {record.get("username", record.get("user_id")): record for record in records}
    return users.get(username, {}).get("password")


def _configured_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=os.getenv("AUTH_USER_ID", "local-handler"),
        role=os.getenv("AUTH_ROLE", "handler"),
        handler_types=frozenset(
            value.strip()
            for value in os.getenv("AUTH_HANDLER_TYPES", "Claims,Motor,Home,Liability,Finance").split(",")
            if value.strip()
        ),
    )


def _users_from_environment() -> dict[str, AuthenticatedUser]:
    raw_users = os.getenv("AUTH_USERS_JSON")
    if not raw_users:
        return {}
    try:
        records = json.loads(raw_users)
    except json.JSONDecodeError as error:
        raise RuntimeError("AUTH_USERS_JSON must contain valid JSON") from error
    return {
        record["token"]: AuthenticatedUser(
            user_id=record["user_id"],
            role=record["role"],
            handler_types=frozenset(record.get("handler_types", [])),
        )
        for record in records
    }


def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthenticatedUser:
    """Validate a simple bearer token for the prototype's API boundary."""
    triage_session = request.cookies.get(SESSION_COOKIE)
    if triage_session:
        session = _sessions.get(triage_session)
        user = session[0] if session and session[1] > time.time() else _decode_session(triage_session)
        if user:
            _current_user.set(user)
            request.state.user = user
            return user
    configured_token = os.getenv("AUTH_TOKEN")
    users = _users_from_environment()
    user = users.get(authorization.removeprefix("Bearer ")) if authorization else None
    if user is None and configured_token and authorization == f"Bearer {configured_token}":
        user = _configured_user()
    if user is None and not configured_token and not users and os.getenv("ENVIRONMENT", "development") == "development":
        user = _configured_user()
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    _current_user.set(user)
    request.state.user = user
    return user


def get_current_user() -> AuthenticatedUser:
    user = _current_user.get()
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_role(*allowed_roles: str) -> None:
    if get_current_user().role == "platform_admin":
        return
    if get_current_user().role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient role permissions")


def require_handler_scope(handler_type: str) -> None:
    user = get_current_user()
    if handler_type not in user.handler_types:
        raise HTTPException(status_code=403, detail="Department is outside the user's scope")


async def authenticate_websocket(websocket: WebSocket) -> bool:
    session_id = websocket.cookies.get(SESSION_COOKIE)
    if session_id:
        session = _sessions.get(session_id)
        user = session[0] if session and session[1] > time.time() else _decode_session(session_id)
        if user:
            _current_user.set(user)
            return True
    configured_token = os.getenv("AUTH_TOKEN")
    if not configured_token and os.getenv("ENVIRONMENT", "development") == "development":
        return True
    authorization = websocket.headers.get("authorization")
    return bool(configured_token and authorization == f"Bearer {configured_token}")


auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@auth_router.get("/demo-users")
async def demo_users():
    if os.getenv("ENVIRONMENT", "development") != "development":
        raise HTTPException(status_code=404, detail="Not found")
    return [
        {"username": username, "password": record["password"], "role": record["role"], "handler_types": record["handler_types"]}
        for username, record in DEFAULT_USERS.items()
    ]


@auth_router.post("/login")
async def login(request: LoginRequest, response: Response):
    expected_password = _password_for_username(request.username)
    if not expected_password or not hmac.compare_digest(request.password, expected_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    user = _user_for_username(request.username)
    session_id = _encode_session(user)
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="lax", max_age=SESSION_TTL_SECONDS)
    return {"user_id": user.user_id, "role": user.role, "handler_types": sorted(user.handler_types)}


@auth_router.post("/logout")
async def logout(response: Response, triage_session: str | None = Cookie(default=None)):
    if triage_session:
        _sessions.pop(triage_session, None)
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "logged_out"}


@auth_router.get("/me")
async def me(user: AuthenticatedUser = Depends(require_auth)):
    current = user
    if not current:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"user_id": current.user_id, "role": current.role, "handler_types": sorted(current.handler_types)}
