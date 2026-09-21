import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConversationSummaryResponse(BaseModel):
    id: uuid.UUID
    title: str | None = None
    created_at: datetime
    last_message_at: datetime | None = None
    message_count: int = 0


class ConversationMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    sources: list[dict[str, Any]] | None = None
    created_at: datetime

    # This reader's own rating, so reopening a conversation shows the
    # thumbs they already gave. Scoped to them: how somebody else rated an
    # answer is not theirs to see.
    feedback: str | None = None


class ConversationDetailResponse(BaseModel):
    id: uuid.UUID
    title: str | None = None
    created_at: datetime
    last_message_at: datetime | None = None
    messages: list[ConversationMessageResponse] = Field(default_factory=list)


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
