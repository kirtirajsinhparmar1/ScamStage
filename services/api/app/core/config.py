from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "SCAMSTAGE"
    use_mock_classifier: bool = True
    use_mock_voice: bool = True
    cors_origins: list[str] = ["http://localhost:3000"]
