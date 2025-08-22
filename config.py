import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    OPENROUTER_API_KEY: str
    OPENAI_API_KEY: str
    BRAVE_API_KEY: str

    MODEL_PROVIDER: str = 'openai'
    ANSWER_MAX_TOKENS: int = 1024
    TEMPERATURE: float = 0.0

    FILESYSTEM_PATH: str = '/Users/alexeyfilichkin/MainDev/web_search_agent'

    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '.env'
            )
    )


settings = Config()
