import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from .config import get_settings
from .services import browser_manager, VacancySearchService, VacancyApplyService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("HHServer")


class ApplyRequest(BaseModel):
    """Тело запроса для отклика на вакансию."""
    url: HttpUrl
    message: str = ""


class ApplyResponse(BaseModel):
    status: str
    message: str


class ErrorResponse(BaseModel):
    error: str
    message: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting browser manager...")
    await browser_manager.start()
    yield
    logger.info("Shutting down browser manager...")
    await browser_manager.stop()


app = FastAPI(
    title="HH.ru Automation API",
    description="Async API for searching and applying to vacancies on HH.ru",
    version="2.0.0",
    lifespan=lifespan
)

# Middleware для CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Экземпляры сервисов
search_service = VacancySearchService()
apply_service = VacancyApplyService()


@app.get("/search")
async def search_vacancies(
    text: str = Query(default="Frontend", description="Search query text"),
    page: int = Query(default=0, ge=0, description="Page number (0-indexed)")
) -> list[dict]:
    """
    Поиск вакансий на HH.ru.
    
    Возвращает список вакансий с заголовком, URL, работодателем и описанием.
    """
    logger.info(f"Search request: text='{text}', page={page}")
    
    try:
        vacancies = await search_service.search(query=text, page_num=page)
        return vacancies
    except FileNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/apply", response_model=ApplyResponse)
async def apply_to_vacancy(request: ApplyRequest) -> ApplyResponse:
    """
    Отклик на вакансию с опциональным сопроводительным письмом.
    
    Возвращает статус и сообщение результата отклика.
    """
    logger.info(f"Apply request: url={request.url}")
    
    try:
        result = await apply_service.apply(str(request.url), request.message)
        return ApplyResponse(**result)
    except Exception as e:
        logger.error(f"Apply failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "session_exists": settings.session_file.exists(),
        "version": "2.0.0"
    }


def run():
    """Запуск сервера."""
    import uvicorn
    settings = get_settings()
    
    logger.info(f"Starting HH Automation API on http://{settings.server_host}:{settings.server_port}")
    logger.info("Endpoints:")
    logger.info("  GET  /search?text=Frontend&page=0")
    logger.info("  POST /apply  { 'url': '...', 'message': '...' }")
    logger.info("  GET  /health")
    logger.info("  GET  /docs  (Swagger UI)")
    
    uvicorn.run(
        app,
        host=settings.server_host,
        port=settings.server_port,
        log_level="info"
    )


if __name__ == "__main__":
    run()
