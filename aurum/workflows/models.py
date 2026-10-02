"""Pydantic models for a workflow definition."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class Step(BaseModel):
    id: str
    method: Literal["GET", "POST", "PUT", "DELETE"] = "GET"
    path: str
    body: dict[str, Any] | None = None
    save_as: str | None = None
    when: str | None = None
    continue_on_error: bool = False

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not _ID.match(v):
            raise ValueError("step id must be lowercase letters, digits, - or _")
        return v


class WorkflowDef(BaseModel):
    id: str
    name: str
    description: str = ""
    schedule: str | None = None
    continue_on_error: bool = False
    steps: list[Step] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not _ID.match(v):
            raise ValueError("workflow id must be lowercase letters, digits, - or _")
        return v
