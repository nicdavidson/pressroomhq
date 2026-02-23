from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    github_token: str = ""
    database_url: str = "sqlite+aiosqlite:///./pressroom.db"
    scout_github_repos: list[str] = ["dreamfactorysoftware/dreamfactory"]
    scout_hn_keywords: list[str] = ["DreamFactory", "REST API", "API gateway"]
    scout_subreddits: list[str] = ["selfhosted", "webdev"]
    scout_rss_feeds: list[str] = []
    claude_model: str = "claude-sonnet-4-20250514"

    class Config:
        env_file = ".env"


settings = Settings()
