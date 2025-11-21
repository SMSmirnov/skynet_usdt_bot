from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass
class Settings:
    bot_token: str
    admin_chat_id: int
    rapira_uid: str
    rapira_public_key: str
    rapira_base_url: str  # <–– добавлено

def get_settings() -> Settings:
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", ""),
        admin_chat_id=int(os.getenv("ADMIN_CHAT_ID", "0")),
        rapira_uid=os.getenv("RAPIRA_UID", ""),
        rapira_public_key=os.getenv("RAPIRA_PUBLIC_KEY", ""),
        rapira_base_url=os.getenv("RAPIRA_BASE_URL", "https://api.rapira.net"),
    )

settings = get_settings()
