from typing import Optional
from pydantic import BaseModel, Field


class ParsedElement(BaseModel):
    id: str
    type: str
    text: str

    page: Optional[int] = None

    metadata: dict = Field(default_factory=dict)


class ParsedDocument(BaseModel):

    filename: str

    parser: str

    elements: list[ParsedElement]

    metadata: dict = Field(default_factory=dict)