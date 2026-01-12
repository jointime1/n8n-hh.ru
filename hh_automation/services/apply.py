"""Асинхронный сервис отклика на вакансии."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from playwright.async_api import Page

from .browser import browser_manager

logger = logging.getLogger(__name__)


class ApplyStatus(str, Enum):
    """Статус коды"""
    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class ApplyResult:
    """Результат попытки отклика на вакансию."""
    status: ApplyStatus
    message: str

    def to_dict(self) -> dict:
        return {"status": self.status.value, "message": self.message}


class VacancyApplyService:
    """Сервис для отклика на вакансии на HH.ru."""

    async def _check_bot_protection(self, page: Page) -> bool:
        """Проверка, сработала ли защита от ботов (капча)."""
        title = await page.title()
        content = await page.content()
        return "captcha" in title.lower() or "robot" in content.lower()

    async def _check_already_applied(self, page: Page) -> bool:
        """Проверка, был ли уже совершен отклик на эту вакансию."""
        locator = page.locator("text=Вы откликнулись")
        return await locator.count() > 0

    async def _fill_cover_letter_modal(
        self,
        page: Page,
        message: str
    ) -> Optional[ApplyResult]:
        """
        Заполнение сопроводительного письма в модальном окне и отправка.
        
        Возвращает:
            ApplyResult в случае успеха, None если взаимодействие с окном не удалось.
        """
        try:
            logger.debug("Waiting for application modal...")
            await page.wait_for_selector("[data-qa='vacancy-response-popup']", timeout=5000)
            await page.wait_for_timeout(1000)
            
            letter_area = page.locator(
                "textarea[data-qa='vacancy-response-popup-form-letter-input']"
            )
            if await letter_area.count() > 0:
                logger.debug(f"Filling cover letter ({len(message)} chars)")
                await letter_area.fill(message)
            else:
                logger.warning("Cover letter field not found in modal")
            
            submit_btn = page.locator("button[data-qa='vacancy-response-submit-popup']")
            if await submit_btn.count() > 0:
                await submit_btn.click()
                await page.wait_for_timeout(3000)
                return ApplyResult(ApplyStatus.SUCCESS, "Applied with cover letter")
            else:
                return ApplyResult(ApplyStatus.ERROR, "Submit button not found")
                
        except Exception as e:
            logger.error(f"Modal interaction failed: {e}")
            return None

    async def _try_cover_letter_link(
        self,
        page: Page,
        message: str
    ) -> Optional[ApplyResult]:
        """Попытка отклика через ссылку 'Написать сопроводительное'."""
        cover_letter_link = page.locator("a:has-text('Написать сопроводительное')")
        
        if await cover_letter_link.count() > 0 and message:
            logger.debug("Found 'Write cover letter' link, clicking...")
            await cover_letter_link.first.click()
            result = await self._fill_cover_letter_modal(page, message)
            if result:
                return result
        
        return None

    async def _try_dropdown_apply(
        self,
        page: Page,
        message: str
    ) -> Optional[ApplyResult]:
        """Попытка отклика через выпадающее меню с опцией сопроводительного письма."""
        dropdown_arrow = page.locator(
            "[data-qa='vacancy-response-link-top'] + button, "
            "[data-qa='vacancy-response-link-bottom'] + button"
        )
        
        if await dropdown_arrow.count() > 0 and message:
            logger.debug("Found dropdown, expanding options...")
            await dropdown_arrow.first.click()
            await page.wait_for_timeout(500)
            
            with_letter_option = page.locator("text=С сопроводительным письмом")
            if await with_letter_option.count() > 0:
                await with_letter_option.first.click()
                result = await self._fill_cover_letter_modal(page, message)
                if result:
                    return result
        
        return None

    async def _try_post_apply_letter(
        self,
        page: Page,
        message: str
    ) -> Optional[ApplyResult]:
        """Попытка заполнения сопроводительного письма на экране после отклика."""
        resume_delivered = page.locator("text=Резюме доставлено")
        
        if await resume_delivered.count() > 0 or await page.locator("textarea").count() > 0:
            logger.debug("Found post-apply screen")
            
            letter_area = page.locator("textarea")
            if await letter_area.count() > 0 and message:
                await letter_area.first.fill(message)
                
                submit_btn = page.locator("button:has-text('Отправить')")
                if await submit_btn.count() > 0:
                    await submit_btn.first.click()
                    await page.wait_for_timeout(2000)
                    return ApplyResult(ApplyStatus.SUCCESS, "Applied with post-apply cover letter")
        
        return None

    async def _check_application_success(self, page: Page) -> bool:
        """Проверка успешности отправки отклика."""
        success_texts = [
            "text=Отклик отправлен",
            "text=Вы откликнулись",
            "text=Резюме доставлено"
        ]
        for selector in success_texts:
            if await page.locator(selector).count() > 0:
                return True
        return False

    async def apply(self, url: str, message: str = "") -> dict:
        """
        Отклик на вакансию с опциональным сопроводительным письмом.
        
        Аргументы:
            url: URL вакансии.
            message: Опциональный текст сопроводительного письма.
            
        Возвращает:
            Словарь со статусом и сообщением.
        """
        logger.info(f"Applying to: {url}")
        if message:
            logger.debug(f"Cover letter: {len(message)} chars")

        try:
            async with browser_manager.get_page(use_session=True) as page:
                # Переход к вакансии
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.warning(f"Navigation timeout: {e}")
                    # Продолжаем в любом случае, страница могла загрузиться достаточно

                # Проверка защиты от ботов
                if await self._check_bot_protection(page):
                    return ApplyResult(
                        ApplyStatus.ERROR,
                        "Bot protection triggered (captcha)"
                    ).to_dict()

                # Проверка, был ли уже отклик
                if await self._check_already_applied(page):
                    return ApplyResult(ApplyStatus.SKIPPED, "Already applied").to_dict()

                # Стратегия 1: Попытка через ссылку сопроводительного письма
                result = await self._try_cover_letter_link(page, message)
                if result:
                    return result.to_dict()

                # Поиск кнопки отклика
                apply_btn = page.locator("[data-qa='vacancy-response-link-top']")
                if await apply_btn.count() == 0:
                    apply_btn = page.locator("[data-qa='vacancy-response-link-bottom']")

                if await apply_btn.count() == 0:
                    return ApplyResult(
                        ApplyStatus.ERROR,
                        "Apply button not found"
                    ).to_dict()

                # Стратегия 2: Попытка через выпадающий список с сопроводительным
                result = await self._try_dropdown_apply(page, message)
                if result:
                    return result.to_dict()

                # Стратегия 3: Стандартная кнопка отклика
                logger.debug("Clicking standard apply button...")
                await apply_btn.first.click()
                await page.wait_for_timeout(2000)

                # Стратегия 4: Сопроводительное письмо после отклика
                result = await self._try_post_apply_letter(page, message)
                if result:
                    return result.to_dict()

                # Проверка успешности отклика
                if await self._check_application_success(page):
                    return ApplyResult(ApplyStatus.SUCCESS, "Applied successfully").to_dict()
                else:
                    return ApplyResult(
                        ApplyStatus.SUCCESS,
                        "Applied (status unclear)"
                    ).to_dict()

        except FileNotFoundError as e:
            return ApplyResult(ApplyStatus.ERROR, str(e)).to_dict()
        except Exception as e:
            logger.error(f"Application failed: {e}", exc_info=True)
            return ApplyResult(ApplyStatus.ERROR, str(e)).to_dict()
