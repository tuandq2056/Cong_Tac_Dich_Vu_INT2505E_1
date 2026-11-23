"""Pydantic schemas for Identity HTTP wire format (OpenAPI-compliant)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


def format_utc_z(dt: datetime) -> str:
    """Format datetime as RFC 3339 UTC ending in Z."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class CredentialsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class PublicUserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    username: str
    created_at: str


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: PublicUserResponse


class GoogleExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str
    state: str
