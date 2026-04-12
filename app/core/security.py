"""
Authentication & Security Configuration.

This module contains security-related configurations and scheme definitions.
"""

from __future__ import annotations

from fastapi.security import OAuth2PasswordBearer

# OAuth2 scheme for bearer token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login/form")
