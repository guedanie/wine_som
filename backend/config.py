from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    anthropic_api_key: str = ""
    grapeminds_api_key: str = ""
    wine_searcher_api_key: str = ""
    apify_api_token: str = ""
    environment: str = "development"

    class Config:
        env_file = "../.env"
        extra = "ignore"


settings = Settings()
