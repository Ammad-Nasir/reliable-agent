import os
from typing import Optional
from pydantic import BaseModel, Field

class Settings(BaseModel):
    PROJECT_NAME: str = "Reliable Customer Remediation Agent"
    VERSION: str = "1.0.0"
    
    # Environment
    ENV: str = Field(default_factory=lambda: os.getenv("ENV", "development"))
    LOG_LEVEL: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    
    # Anthropic / Claude API
    ANTHROPIC_API_KEY: Optional[str] = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", None))
    CLAUDE_MODEL: str = Field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-3-7-sonnet-20250219"))
    
    # Database (Postgres with SQLite fallback)
    DATABASE_URL: str = Field(default_factory=lambda: os.getenv(
        "DATABASE_URL", 
        "postgresql+psycopg://postgres:postgres@localhost:5432/agent_db"
    ))
    SQLITE_FALLBACK_URL: str = "sqlite+aiosqlite:///./agent_data.db"
    USE_SQLITE_FALLBACK: bool = Field(default_factory=lambda: os.getenv("USE_SQLITE_FALLBACK", "true").lower() in ("true", "1"))
    
    # Redis (with in-memory dictionary fallback)
    REDIS_URL: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    USE_REDIS_FALLBACK: bool = Field(default_factory=lambda: os.getenv("USE_REDIS_FALLBACK", "true").lower() in ("true", "1"))
    
    # Celery
    CELERY_BROKER_URL: str = Field(default_factory=lambda: os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"))
    CELERY_RESULT_BACKEND: str = Field(default_factory=lambda: os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"))
    
    # Risk Guardrails & Agent Configuration
    HIGH_RISK_REFUND_THRESHOLD: float = Field(default_factory=lambda: float(os.getenv("HIGH_RISK_REFUND_THRESHOLD", "50.0")))
    MAX_STEPS_LIMIT: int = Field(default_factory=lambda: int(os.getenv("MAX_STEPS_LIMIT", "10")))
    MAX_IDENTICAL_TOOL_CALLS: int = Field(default_factory=lambda: int(os.getenv("MAX_IDENTICAL_TOOL_CALLS", "3")))
    
    # Cost Estimation Constants (USD per 1M tokens for Claude 3.7 Sonnet)
    INPUT_TOKEN_COST_PER_M: float = 3.00
    OUTPUT_TOKEN_COST_PER_M: float = 15.00

settings = Settings()
