import os
from typing import List, Optional
from pydantic import BaseSettings


class Settings(BaseSettings):
    # Telegram Bot Configuration
    telegram_bot_token: str
    webhook_url: str
    
    # Database Configuration
    database_url: str
    
    # Redis Configuration (optional)
    redis_url: Optional[str] = None
    
    # Security
    secret_key: str
    
    # Game Configuration
    question_timeout: int = 30
    total_gates: int = 100
    prize_pool_percentage: int = 69
    
    # Admin Configuration
    admin_telegram_ids: List[int] = []
    
    class Config:
        env_file = ".env"
        
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Parse admin IDs from comma-separated string
        if isinstance(self.admin_telegram_ids, str):
            self.admin_telegram_ids = [
                int(x.strip()) for x in self.admin_telegram_ids.split(",") 
                if x.strip().isdigit()
            ]
        
        # Handle Railway's DATABASE_URL format
        if self.database_url and self.database_url.startswith('postgres://'):
            self.database_url = self.database_url.replace('postgres://', 'postgresql://', 1)


# Global settings instance
settings = Settings() 