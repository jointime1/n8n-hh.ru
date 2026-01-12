import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):

    # Конфигурация сервера
    server_host: str = Field(default="127.0.0.1", alias="SERVER_HOST")
    server_port: int = Field(default=8000, alias="SERVER_PORT")

    n8n_files_dir: Path = Field(
        default_factory=lambda: Path.home() / ".n8n-files",
        alias="N8N_FILES_DIR"
    )

    # Настройки поиска
    default_search_text: str = Field(default="Frontend", alias="DEFAULT_SEARCH_TEXT")
    area_code: str = Field(default="113", alias="AREA_CODE")  # Russia

    # Настройки браузера
    browser_headless: bool = Field(default=True, alias="BROWSER_HEADLESS")
    browser_slow_mo: int = Field(default=0, alias="BROWSER_SLOW_MO")
    page_timeout: int = Field(default=30000, alias="PAGE_TIMEOUT")

    @property
    def session_file(self) -> Path:
        """Путь к сессии Playwright."""
        return self.n8n_files_dir / "hh_session.json"

    def ensure_dirs(self) -> None:
        """Если папки для ссессии нет, создаем."""
        self.n8n_files_dir.mkdir(parents=True, exist_ok=True)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
