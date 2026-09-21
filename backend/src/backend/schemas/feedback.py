"""
Request and response models for answer ratings.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.db.models import MAX_COMMENT_LENGTH


class FeedbackRequest(BaseModel):
    message_id: int
    rating: Literal["up", "down"]

    # Optional, and bounded. This is a rating with a note, not a second
    # chat: anything longer belongs in a message.
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_LENGTH)

    @field_validator("comment")
    @classmethod
    def blank_is_absent(cls, value: str | None) -> str | None:
        """An empty box is no comment, not an empty one."""

        if value is None:
            return None

        stripped = value.strip()

        return stripped or None


class FeedbackResponse(BaseModel):
    message_id: int
    rating: str
    comment: str | None = None
    created_at: datetime
    updated_at: datetime
