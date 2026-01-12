"""Асинхронный сервис поиска вакансий."""

import logging
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Page

from ..config import get_settings
from .browser import browser_manager

logger = logging.getLogger(__name__)


@dataclass
class Vacancy:
    """Модель данных вакансии."""
    title: str
    url: str
    employer: str
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "employer": self.employer,
            "description": self.description
        }


class VacancySearchService:
    """Сервис для поиска вакансий на HH.ru."""

    def __init__(self) -> None:
        self._settings = get_settings()

    async def _get_vacancy_description(self, page: Page, url: str) -> str:
        """
        Переход на страницу вакансии и извлечение полного описания.
        
        Аргументы:
            page: Страница браузера для использования.
            url: URL вакансии.
            
        Возвращает:
            Полный текст описания вакансии.
        """
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_selector("[data-qa='vacancy-description']", timeout=10000)
            
            description_el = page.locator("[data-qa='vacancy-description']")
            if await description_el.count() > 0:
                return (await description_el.inner_text()).strip()
            return ""
            
        except Exception as e:
            logger.warning(f"Failed to get description for {url}: {e}")
            return ""

    async def _check_bot_protection(self, page: Page) -> bool:
        """Проверка, сработала ли защита от ботов (капча)."""
        title = await page.title()
        content = await page.content()
        return "captcha" in title.lower() or "robot" in content.lower()

    async def search(
        self,
        query: Optional[str] = None,
        page_num: int = 0
    ) -> list[dict]:
        """
        Поиск вакансий, соответствующих запросу.
        
        Аргументы:
            query: Текст запроса. По умолчанию используется значение из настроек.
            page_num: Номер страницы для пагинации (начиная с 0).
            
        Возвращает:
            Список словарей вакансий с заголовком, URL, работодателем и описанием.
            
        Исключения:
            RuntimeError: Если сработала защита от ботов.
            FileNotFoundError: Если файл сессии не найден.
        """
        query = query or self._settings.default_search_text
        
        logger.info(f"Searching vacancies: query='{query}', page={page_num}")

        async with browser_manager.get_page(use_session=True) as page:
            # Сборка URL для поиска
            url = (
                f"https://hh.ru/search/vacancy?"
                f"text={query}&area={self._settings.area_code}"
                f"&items_on_page=20&page={page_num}"
            )
            
            await page.goto(url, wait_until="domcontentloaded")
            
            if await self._check_bot_protection(page):
                raise RuntimeError("Bot protection triggered (captcha detected)")

            # Ожидание результатов
            await page.wait_for_selector("[data-qa='vacancy-serp__vacancy']", timeout=10000)
            
            # Сбор основных данных вакансий из результатов поиска
            vacancy_data: list[dict] = []
            cards = await page.locator("[data-qa='vacancy-serp__vacancy']").all()
            
            for i, card in enumerate(cards):
                try:
                    title_el = card.locator("[data-qa='serp-item__title']")
                    await title_el.wait_for(state="visible", timeout=5000)
                    
                    href = await title_el.get_attribute("href")
                    title = await title_el.inner_text()
                    
                    employer_el = card.locator("[data-qa='vacancy-serp__vacancy-employer']").first
                    employer = (
                        await employer_el.inner_text() 
                        if await employer_el.count() > 0 
                        else "Unknown"
                    )
                    
                    vacancy_data.append({
                        "title": title,
                        "url": href,
                        "employer": employer
                    })
                    
                except Exception as e:
                    logger.warning(f"Failed to parse vacancy card {i}: {e}")
                    continue

            # Получение полных описаний для каждой вакансии
            vacancies: list[dict] = []
            for data in vacancy_data:
                description = await self._get_vacancy_description(page, data["url"])
                vacancy = Vacancy(
                    title=data["title"],
                    url=data["url"],
                    employer=data["employer"],
                    description=description
                )
                vacancies.append(vacancy.to_dict())

            logger.info(f"Found {len(vacancies)} vacancies")
            return vacancies
