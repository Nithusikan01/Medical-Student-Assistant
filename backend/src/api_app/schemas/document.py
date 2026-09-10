from pydantic import BaseModel


class IngestResponse(BaseModel):
    filename: str
    status: str
    message: str
