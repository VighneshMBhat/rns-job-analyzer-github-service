from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "GitHub Skill Extractor"
    HOST_URL: str = "http://localhost:8001"
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Supabase (required)
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    
    # GitHub OAuth (optional - can be fetched from database)
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = ""
    
    # Groq API (optional - can be fetched from database)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama3-70b-8192"

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"


settings = Settings()
