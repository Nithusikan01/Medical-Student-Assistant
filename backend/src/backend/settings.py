"""
Where the engine's configuration comes from.

The rag package parses a mapping and never reads the environment itself;
this application decides that the mapping is the process environment
(populated from backend/.env at startup).
"""

import os

from rag.config.settings import Settings, settings_from_mapping


def load_settings() -> Settings:
    return settings_from_mapping(os.environ)
