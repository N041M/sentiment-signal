import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://sentiment:sentiment@localhost:5432/sentiment_signal"

    newsapi_key: str = ""
    fred_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "SentimentSignal/0.1"
    youtube_api_key: str = ""
    bluesky_handle: str = ""
    bluesky_app_password: str = ""

    wandb_project: str = "sentiment-signal"
    wandb_api_key: str = ""

    hf_token: str = ""

    nlp_batch_size: int = 32
    embedding_dim: int = 768
    reaction_window_hours: int = 48


settings = Settings()

# HuggingFace libraries read this env var directly at import time
if settings.hf_token:
    os.environ.setdefault("HF_TOKEN", settings.hf_token)
