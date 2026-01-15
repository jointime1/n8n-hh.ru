"""Асинхронный сервис отклика на вакансии."""
import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

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

    async def _save_screenshot(self, page: Page, reason: str) -> None:
        """Сохранение скриншота в папку screenshots для диагностики ошибок."""
        safe_reason = re.sub(r"[^a-zA-Z0-9_-]+", "_", reason).strip("_").lower() or "error"
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        screenshots_dir = Path("screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshots_dir / f"{timestamp}_{safe_reason}.png"
        try:
            await page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info(f"Saved screenshot: {screenshot_path}")
        except Exception as e:
            logger.warning(f"Failed to save screenshot: {e}")

    async def _check_bot_protection(self, page: Page) -> bool:
        """Проверка, сработала ли защита от ботов (капча)."""
        title = await page.title()
        content = await page.content()
        triggered = "captcha" in title.lower() or "robot" in content.lower()
        logger.debug(f"Bot protection check: {triggered}")
        return triggered

    async def _check_already_applied(self, page: Page) -> bool:
        """Проверка, был ли уже совершен отклик на эту вакансию."""
        locator = page.locator("text=Вы откликнулись")
        count = await locator.count()
        logger.debug(f"Already applied check: {count} matches")
        return count > 0

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
            await asyncio.sleep(1)
            await page.wait_for_selector('div[data-qa="modal-overlay"]', timeout=5000)

            modal = page.locator('div[data-qa="modal-overlay"]')
            add_letter_btn = modal.locator("text=Добавить сопроводительное")
            add_letter_count = await add_letter_btn.count()
            logger.debug(f"Modal 'add cover letter' button count: {add_letter_count}")
            if add_letter_count > 0:
                await add_letter_btn.first.scroll_into_view_if_needed()
                await add_letter_btn.first.click()
                logger.debug("Modal 'add cover letter' clicked")
                await page.wait_for_timeout(500)

            letter_area = modal.locator(
                "textarea[data-qa='vacancy-response-popup-form-letter-input']"
            )
            letter_area_count = await letter_area.count()
            logger.debug(f"Modal letter textarea count: {letter_area_count}")
            if letter_area_count > 0:
                logger.debug(f"Filling cover letter ({len(message)} chars)")
                await letter_area.fill(message)
            else:
                logger.warning("Cover letter field not found in modal")

            submit_btn = modal.locator("text=Откликнуться")
            submit_btn_count = await submit_btn.count()
            logger.debug(f"Modal submit button count: {submit_btn_count}")
            if submit_btn_count > 0:
                await submit_btn.first.scroll_into_view_if_needed()
                await submit_btn.click()
                logger.debug("Modal submit clicked")
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
        cover_letter_link_count = await cover_letter_link.count()
        logger.debug(f"Cover letter link count: {cover_letter_link_count}")

        if cover_letter_link_count > 0 and message:
            logger.debug("Found 'Write cover letter' link, clicking...")
            await cover_letter_link.first.click()
            result = await self._fill_cover_letter_modal(page, message)
            if result:
                return result
        elif cover_letter_link_count > 0 and not message:
            logger.debug("Cover letter link found but message is empty")

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
        dropdown_count = await dropdown_arrow.count()
        logger.debug(f"Dropdown arrow count: {dropdown_count}")

        if dropdown_count > 0 and message:
            logger.debug("Found dropdown, expanding options...")
            await dropdown_arrow.first.click()
            await page.wait_for_timeout(500)

            with_letter_option = page.locator("text=С сопроводительным письмом")
            with_letter_count = await with_letter_option.count()
            logger.debug(f"Dropdown 'with letter' option count: {with_letter_count}")
            if with_letter_count > 0:
                await with_letter_option.first.click()
                result = await self._fill_cover_letter_modal(page, message)
                if result:
                    return result
        elif dropdown_count > 0 and not message:
            logger.debug("Dropdown found but message is empty")

        return None

    async def _try_post_apply_letter(
        self,
        page: Page,
        message: str
    ) -> Optional[ApplyResult]:
        """Попытка заполнения сопроводительного письма на экране после отклика."""
        resume_delivered = page.locator("text=Резюме доставлено")
        resume_delivered_count = await resume_delivered.count()
        textarea_count = await page.locator("textarea").count()
        logger.debug(
            f"Post-apply screen check: resume_delivered={resume_delivered_count}, "
            f"textarea={textarea_count}"
        )

        if resume_delivered_count > 0 or textarea_count > 0:
            logger.debug("Found post-apply screen")

            letter_area = page.locator("textarea")
            letter_area_count = await letter_area.count()
            logger.debug(f"Post-apply textarea count: {letter_area_count}")
            if letter_area_count > 0 and message:
                await letter_area.first.fill(message)
                logger.debug("Post-apply cover letter filled")

                submit_btn = page.locator("button:has-text('Отправить')")
                submit_btn_count = await submit_btn.count()
                logger.debug(f"Post-apply submit button count: {submit_btn_count}")
                if submit_btn_count > 0:
                    await submit_btn.first.click()
                    logger.debug("Post-apply submit clicked")
                    await page.wait_for_timeout(2000)
                    return ApplyResult(ApplyStatus.SUCCESS, "Applied with post-apply cover letter")
            elif letter_area_count > 0 and not message:
                logger.debug("Post-apply textarea found but message is empty")

        return None

    async def _check_application_success(self, page: Page) -> bool:
        """Проверка успешности отправки отклика."""
        success_texts = [
            "text=Отклик отправлен",
            "text=Вы откликнулись",
            "text=Резюме доставлено"
        ]
        for selector in success_texts:
            count = await page.locator(selector).count()
            logger.debug(f"Success selector '{selector}' count: {count}")
            if count > 0:
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

        page = None
        try:
            async with browser_manager.get_page(use_session=True) as page:
                # Переход к вакансии
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeoutError as e:
                    logger.warning(f"Navigation timeout: {e}")
                    await self._save_screenshot(page, "navigation_timeout")
                    # Продолжаем в любом случае, страница могла загрузиться достаточно
                except Exception as e:
                    logger.warning(f"Navigation error: {e}")
                    await self._save_screenshot(page, "navigation_error")

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
                apply_btn = page.locator("[data-qa='vacancy-response-link-top']:visible")
                apply_top_count = await apply_btn.count()
                logger.debug(f"Apply top button count: {apply_top_count}")
                if apply_top_count == 0:
                    apply_btn = page.locator("[data-qa='vacancy-response-link-bottom']:visible")

                apply_bottom_count = await apply_btn.count()
                logger.debug(f"Apply bottom button count: {apply_bottom_count}")
                if apply_bottom_count == 0:
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
                logger.debug("Standard apply button clicked")

                # Стратегия 4: Модальное окно после отклика
                try:
                    result = await self._fill_cover_letter_modal(page, message)
                    if result:
                        return result.to_dict()
                except PlaywrightTimeoutError:
                    logger.debug("Application modal not detected after apply click")

                # Стратегия 5: Сопроводительное письмо после отклика
                result = await self._try_post_apply_letter(page, message)
                if result:
                    return result.to_dict()

                # Проверка успешности отклика
                if await self._check_application_success(page):
                    return ApplyResult(ApplyStatus.SUCCESS, "Applied successfully").to_dict()
                else:
                    await self._save_screenshot(page, "status unclear")
                    return ApplyResult(
                        ApplyStatus.SUCCESS,
                        "Applied (status unclear)"
                    ).to_dict()

        except FileNotFoundError as e:
            return ApplyResult(ApplyStatus.ERROR, str(e)).to_dict()
        except Exception as e:
            logger.error(f"Application failed: {e}", exc_info=True)
            if page is not None:
                await self._save_screenshot(page, "apply_error")
            return ApplyResult(ApplyStatus.ERROR, str(e)).to_dict()
