from functools import lru_cache

from rag_application.config.settings import load_settings


@lru_cache()
def get_settings():
    return load_settings()