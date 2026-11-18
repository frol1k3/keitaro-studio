from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    keitaro_base_url: str = ""
    keitaro_api_key: str = ""
    database_url: str = "sqlite:///./keitaro_wrapper.db"
    campaign_prefix: str = "test_frolov_"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def configured(self) -> bool:
        return bool(self.keitaro_base_url and self.keitaro_api_key)

