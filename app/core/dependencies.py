"""
Dependency Injection Container.

This module re-exports all dependencies and factories for use in FastAPI endpoints.
It provides a single entry point for accessing all injected dependencies.

For maintainability, specific dependencies are organized into separate modules:
  - factories.py: Repository and service factories
  - security.py: Security configuration (OAuth2 scheme)
  - guards.py: Auth guards and RBAC logic
"""

from __future__ import annotations

# Re-export repository factories
from app.core.factories import (
    get_audit_repository,
    get_audit_service,
    get_auth_service,
    get_token_cache,
    get_token_repository,
    get_user_repository,
    get_user_service,
)

# Re-export auth guards and aliases
from app.core.guards import (
    AdminUser,
    CurrentUser,
    get_current_active_user,
    get_current_user,
    require_roles,
)

# Re-export security configuration
from app.core.security import oauth2_scheme

__all__ = [
    # Factories
    "get_user_repository",
    "get_audit_repository",
    "get_token_repository",
    "get_token_cache",
    "get_auth_service",
    "get_user_service",
    "get_audit_service",
    # Guards
    "get_current_user",
    "get_current_active_user",
    "require_roles",
    "CurrentUser",
    "AdminUser",
    # Security
    "oauth2_scheme",
]
