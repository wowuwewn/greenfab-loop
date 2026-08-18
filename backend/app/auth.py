"""Minimal API-key authentication and role authorization boundary."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Security
from fastapi.security import APIKeyHeader

from app.config import settings
from app.enums import ApiRole
from app.errors import DomainError


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    actor: str
    role: ApiRole
    key_id: str | None
    is_demo: bool = False


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_ROLE_LEVEL = {
    ApiRole.VIEWER: 0,
    ApiRole.OPERATOR: 1,
    ApiRole.DECISION_MAKER: 2,
    ApiRole.ADMIN: 3,
}


def get_principal(
    api_key: Annotated[str | None, Security(_api_key_header)],
    x_actor: Annotated[
        str | None,
        Header(alias="X-Actor", min_length=1, max_length=120, pattern=r".*\S.*"),
    ] = None,
) -> AuthPrincipal:
    """Authenticate a request or provide the explicitly configured demo principal."""

    if settings.auth_mode == "demo":
        actor = (x_actor or settings.demo_actor).strip()
        return AuthPrincipal(actor=actor, role=ApiRole.ADMIN, key_id=None, is_demo=True)

    if api_key is None or not 16 <= len(api_key) <= 512:
        raise DomainError("AUTH_REQUIRED", "유효한 X-API-Key가 필요합니다.", 401)
    supplied_digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    for credential in settings.api_key_credentials:
        if hmac.compare_digest(supplied_digest, credential.secret_sha256.casefold()):
            return AuthPrincipal(
                actor=credential.actor,
                role=credential.role,
                key_id=credential.key_id,
            )
    raise DomainError("AUTH_REQUIRED", "유효한 X-API-Key가 필요합니다.", 401)


Principal = Annotated[AuthPrincipal, Depends(get_principal)]


def require_min_role(minimum_role: ApiRole):
    """Create a dependency enforcing the role hierarchy."""

    def dependency(principal: Principal) -> AuthPrincipal:
        if _ROLE_LEVEL[principal.role] < _ROLE_LEVEL[minimum_role]:
            raise DomainError("FORBIDDEN", "이 작업을 수행할 권한이 없습니다.", 403)
        return principal

    return dependency


def require_min_role_without_actor_override(minimum_role: ApiRole):
    """Authorize a principal while ignoring the demo-only ``X-Actor`` header.

    Demand/index administration always records the configured principal actor,
    even in demo mode, so an arbitrary header cannot spoof its audit trail.
    """

    def dependency(
        api_key: Annotated[str | None, Security(_api_key_header)],
    ) -> AuthPrincipal:
        principal = get_principal(api_key, None)
        if _ROLE_LEVEL[principal.role] < _ROLE_LEVEL[minimum_role]:
            raise DomainError("FORBIDDEN", "이 작업을 수행할 권한이 없습니다.", 403)
        return principal

    return dependency
