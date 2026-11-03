"""Pydantic request/response models.

Semantic validation (URL shape, expiry rules) lives in the service layer so
those errors use the consistent 400 JSON error format.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CreateURLRequest(BaseModel):
    url: str
    expires_at: Optional[datetime] = None
    ttl_seconds: Optional[int] = None


class CreateURLResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime] = None


class StatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    short_code: str
    original_url: str
    click_count: int
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool
    last_accessed_at: Optional[datetime] = None
