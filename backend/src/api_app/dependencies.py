from functools import lru_cache
from fastapi import Request

from rag_application.config.settings import load_settings


@lru_cache()
def get_settings():
    return load_settings()


def get_rag_service(request: Request):
    return request.app.state.rag_service