# HH.ru Automation

Асинхронная автоматизация поиска и откликов на вакансии HH.ru через Python + n8n + Google Gemini AI.

### Ссылка на видео с гайдом: https://www.youtube.com/watch?v=EakL7eoSL9U

**Не хотите запариваться с развёртыванием?** Есть готовый Telegram-бот: [@roaster_resume_bot](https://t.me/roaster_resume_bot)

**И платформа моя, вот: https://jobturbo.ru/**

## Особенности v2.0

- ⚡ **Async FastAPI** 
- 🎭 **Async Playwright** 
- 📖 **Swagger UI** — автодокументация API на `/docs`

## Установка

### 1. Создание виртуального окружения

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# или
.venv\Scripts\activate     # Windows
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Настройка окружения

Создайте файл `.env` в корне проекта:

```env
# Путь к директории для хранения сессии
N8N_FILES_DIR=/Users/your_username/.n8n-files

# Настройки сервера
SERVER_HOST=127.0.0.1
SERVER_PORT=8000

# Настройки поиска
DEFAULT_SEARCH_TEXT=Frontend
AREA_CODE=113

# Настройки браузера (опционально)
BROWSER_HEADLESS=true
BROWSER_SLOW_MO=0
PAGE_TIMEOUT=30000
```

**Важно:** Замените `/Users/your_username/.n8n-files` на реальный путь.

## Запуск

### Вариант 1: Запуск через Docker (рекомендуется)

Docker позволяет запустить приложение без установки Python и зависимостей на вашу систему.

#### Требования

- Docker Desktop (для Windows/Mac) или Docker Engine (для Linux)
- docker-compose (обычно идет в комплекте с Docker Desktop)

#### 1. Сборка и запуск контейнеров

В корневой директории проекта выполните:

```bash
docker-compose up -d
```

Эта команда:
- Соберет Docker образ приложения
- Запустит два контейнера: `hh-automation` (API сервер) и `n8n` (workflow система)
- Сервер HH Automation будет доступен на `http://localhost:8000`
- n8n будет доступен на `http://localhost:5678`

#### 2. Авторизация на HH.ru

После запуска контейнеров необходимо авторизоваться на HH.ru **один раз**:

```bash
docker exec -it hh-automation python -m hh_automation.cli.login
```

Откроется браузер. Войдите в аккаунт HH.ru, затем нажмите Enter в терминале. Сессия сохранится в директории `./data/hh_session.json`.

#### 3. Настройка n8n

1. Откройте `http://localhost:5678` в браузере
2. Создайте учетную запись n8n (при первом запуске)
3. Импортируйте workflow из файла `HH.ru Flow (With AI and Pagination).json`
4. Добавьте Google Gemini API credentials в n8n (Settings → Credentials)
5. Запустите workflow

P.S. Если не запускается workflow с сервером, поменяйте в узлах адрес сервера на `http://hh-automation:8000`
#### 4. Управление контейнерами

**Просмотр логов:**
```bash
# Все сервисы
docker-compose logs -f

# Только HH Automation
docker-compose logs -f hh-automation

# Только n8n
docker-compose logs -f n8n
```

**Остановка:**
```bash
docker-compose down
```

**Перезапуск после изменения кода:**
```bash
docker-compose restart hh-automation
```

**Полная пересборка образа:**
```bash
docker-compose up -d --build
```

#### 5. Проверка работоспособности

```bash
# Проверка API
curl http://localhost:8000/health

# Swagger документация
# Откройте в браузере: http://localhost:8000/docs
```

### Вариант 2: Запуск локально (без Docker)

#### 1. Авторизация на HH.ru

Перед первым использованием сохраните сессию:

```bash
python -m hh_automation.cli.login
```

Откроется браузер. Войдите в аккаунт HH.ru, затем нажмите Enter в терминале.

#### 2. Запуск сервера

```bash
python -m hh_automation.server
```

Сервер запустится на `http://127.0.0.1:8000`.

#### 3. Настройка n8n

1. Импортируйте workflow из файла `HH.ru Flow (With AI and Pagination).json`
2. Добавьте Google Gemini API credentials в n8n (Settings → Credentials)
3. Запустите workflow

## API Endpoints

### GET /search

Поиск вакансий.

**Параметры:**
- `text` — поисковый запрос (по умолчанию: "Frontend")
- `page` — номер страницы, начиная с 0 (по умолчанию: 0)
- `work_format` — фильтр по формату работы (REMOTE/FIELD_WORK/ON_SITE/HYBRID, можно передавать несколько раз)
- `experience` — фильтр по опыту (moreThan6/between3And6/between1And3/noExperience)

**Пример:**
```bash
curl "http://127.0.0.1:8000/search?text=Python&page=0"
```

**Пример с фильтрами формата работы:**
```bash
curl "http://127.0.0.1:8000/search?text=Python&page=0&work_format=REMOTE&work_format=HYBRID"
```

**Пример с фильтром опыта:**
```bash
curl "http://127.0.0.1:8000/search?text=Python&page=0&experience=between1And3"
```

### POST /apply

Отклик на вакансию.

**Body:**
```json
{
  "url": "https://hh.ru/vacancy/123456",
  "message": "Текст сопроводительного письма"
}
```

**Пример:**
```bash
curl -X POST http://127.0.0.1:8000/apply \
  -H "Content-Type: application/json" \
  -d '{"url": "https://hh.ru/vacancy/123456", "message": "Здравствуйте..."}'
```

### GET /health

Проверка состояния сервера.

**Пример:**
```bash
curl http://127.0.0.1:8000/health
```

### GET /docs

Swagger UI с интерактивной документацией API.

## Структура проекта

```
.
├── hh_automation/
│   ├── __init__.py
│   ├── config.py           # Централизованная конфигурация
│   ├── server.py           # FastAPI сервер
│   ├── services/
│   │   ├── __init__.py
│   │   ├── browser.py      # Async Playwright менеджер
│   │   ├── search.py       # Сервис поиска вакансий
│   │   └── apply.py        # Сервис откликов
│   └── cli/
│       ├── __init__.py
│       └── login.py        # CLI для авторизации
├── requirements.txt
├── .env                    # Конфигурация (создать вручную)
└── HH.ru Flow (With AI and Pagination).json  # n8n workflow
```

## Миграция с v1.0

Старые файлы (`hh_server.py`, `hh_login.py`, `search_vacancies.py`, `apply_vacancy.py`) 
можно удалить после успешного тестирования новой версии.

**Изменения API:**
- Эндпоинты остались теми же (`/search`, `/apply`)
- Добавлен `/health` эндпоинт
- Добавлен Swagger UI на `/docs`

## Troubleshooting

### Session file not found

```bash
python -m hh_automation.cli.login
```

### Playwright browser not found

```bash
playwright install chromium
```

### ModuleNotFoundError

Убедитесь, что виртуальное окружение активировано:
```bash
source .venv/bin/activate
```

### Ошибка импорта pydantic-settings

```bash
pip install pydantic-settings
```

## Ограничения

- Нет обработки rate limiting от HH.ru
- Требуется периодическое обновление сессии
- Captcha не обрабатывается автоматически

## Google Gemini API

Получите API ключ: [Google AI Studio](https://makersuite.google.com/app/apikey)

Бесплатный tier: 60 запросов/минуту (достаточно для автоматизации).

## Рекомендации

1. Не превышайте 3-5 страниц за один запуск (60-100 вакансий)
2. Используйте задержки между откликами (минимум 5 секунд)
3. Обновляйте сессию раз в неделю через `python -m hh_automation.cli.login`
4. Мониторьте статистику откликов в личном кабинете HH.ru
