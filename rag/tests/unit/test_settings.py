import pytest

from rag_application.config.settings import load_settings


def test_missing_api_key(monkeypatch):
    # Remove environment variables if they exist
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    monkeypatch.delenv("PINECONE_INDEX_NAME", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    # Attempt to load settings, expecting a ValueError due to missing API key
    with pytest.raises(ValueError):
        load_settings()


def test_load_settings(monkeypatch):
    # Set environment variables for testing
    monkeypatch.setenv("PINECONE_API_KEY", "test_api_key")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "test_index_name")
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_api_key")

    # Load settings
    settings = load_settings()

    # Assert that the settings are loaded correctly
    assert settings.pinecone_api_key == "test_api_key"
    assert settings.pinecone_index_name == "test_index_name"
    assert settings.gemini_api_key == "test_gemini_api_key"
