import asyncio
import json
import sys
from typing import Optional

from ..config import get_settings
from ..services.browser import BrowserManager


async def login() -> None:
    """
    Открывает окно браузера для ручного входа на HH.ru и сохраняет
    состояние сессии для последующего автоматического использования.
    """
    settings = get_settings()
    settings.ensure_dirs()
    
    manager = BrowserManager()
    
    async with manager.get_interactive_context() as (context, page):
        await page.goto("https://hh.ru/login")
        
        print("\n" + "=" * 60)
        print("HH.ru Login")
        print("=" * 60)
        print("\n1. Log in to HH.ru in the opened browser window")
        print("2. Wait until you see your personal profile or resumes page")
        print("3. Come back here and press Enter to save the session")
        print("\n" + "-" * 60)
        
        # Ожидание завершения входа пользователем
        input("\nPress Enter after you have successfully logged in...")
        
        # Получение User-Agent для конфигурации n8n
        user_agent = await page.evaluate("navigator.userAgent")
        
        print("\n" + "=" * 60)
        print("IMPORTANT: Use this User-Agent in n8n HTTP headers:")
        print("-" * 60)
        print(user_agent)
        print("=" * 60)
        
        # Сохранение состояния сессии
        await context.storage_state(path=str(settings.session_file))
        print(f"\n✓ Session saved to: {settings.session_file}")
        print("  You can now start the server with: python -m hh_automation.server")


def get_cookies() -> Optional[str]:
    """
    Извлечение куки из сохраненной сессии в виде строки.
    
    Возвращает:
        Строку куки, отформатированную для HTTP-заголовков, или None, если сессия не найдена.
    """
    settings = get_settings()
    
    if not settings.session_file.exists():
        print("No session file found. Run login first.", file=sys.stderr)
        return None
    
    with open(settings.session_file, "r") as f:
        state = json.load(f)
        cookies = state.get("cookies", [])
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def main() -> None:
    """Точка входа CLI."""
    if len(sys.argv) > 1 and sys.argv[1] == "--get-cookies":
        result = get_cookies()
        if result:
            print(result)
    else:
        asyncio.run(login())


if __name__ == "__main__":
    main()
