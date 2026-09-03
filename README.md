# Scientific Research Graph

Scientific Research Graph — приложение для поиска и анализа научных публикаций вокруг заданной
области исследования. Пользователь загружает матрицу Related Work, формулирует исследовательские
вопросы, а система находит исходные статьи в Semantic Scholar, исследует связи первого уровня в
графе цитирования и формирует ранжированную карту релевантных работ.

Ранжирование объединяет семантическую близость к исследовательским вопросам, научное влияние и
положение статьи в графе. Результаты сохраняются в PostgreSQL и доступны без повторного запуска
исследования: их можно фильтровать по итоговой оценке, году, числу цитирований, глубине, категории
и типу статьи.

Веб-интерфейс показывает состояние фонового задания, итоговый рейтинг и интерактивный
ориентированный граф. Выбор публикации открывает её метаданные, составные оценки и релевантность
по каждому исследовательскому вопросу.

Система построена на FastAPI, Next.js, PostgreSQL с pgvector, Redis и Cytoscape.js. Исследовательский
pipeline включает разрешение исходных публикаций, дедупликацию, сбор citation neighborhood,
построение embeddings, семантическое ранжирование, анализ графа и расчёт итоговой оценки.

Текущий MVP покрывает полный путь от загрузки XLSX/CSV до сохранённого ranking и Graph UI.
Следующий этап — сквозная проверка Docker Compose окружения и эксплуатационное укрепление приложения.

## Документация

- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — настройка окружения, локальный и Docker Compose запуск,
  миграции, автоматические проверки, acceptance flow и диагностика.
- [`docs/SCORING.md`](docs/SCORING.md) — назначение метрик, формулы, веса, missing-value policy
  и пример расчёта статьи.
- [`docs/related_work_matrix.md`](docs/related_work_matrix.md) — формат и правила заполнения
  матрицы Related Work.

## Как формируется рейтинг

| Score | Назначение |
|---|---|
| Topic | Семантическая близость к research questions и seed papers |
| Impact | Нормализованные citations, актуальность и PageRank |
| Graph | Близость к seed papers и связность внутри citation graph |
| Final | `0.60 × Topic + 0.25 × Impact + 0.15 × Graph` |

Таблица сортируется по Final score по убыванию. Отсутствующие компоненты не считаются нулём:
их веса исключаются и перераспределяются между доступными значениями. Подробное описание всех
метрик и пример расчёта приведены в [`docs/SCORING.md`](docs/SCORING.md).

## Архитектура текущего этапа

- `backend/app/api` — только HTTP и health checks.
- `backend/app/domain` — framework-independent глобальные и project-specific модели.
- `backend/app/research` — discovery, embeddings, semantic, graph, impact и final ranking.
- `backend/app/providers` — Semantic Scholar HTTP adapter.
- `backend/app/repositories` — graph, embedding, score и ResearchJob persistence.
- `backend/app/application` — создание job и постановка в Redis queue.
- `backend/app/infrastructure` — PostgreSQL и Redis adapters.
- `backend/app/workers` — Redis worker, запускающий текущий `ResearchPipeline`.
- `backend/migrations` — Alembic schema с graph, project data и pgvector embeddings.
- `frontend/src/api` — типизированный HTTP client и API contracts.
- `frontend/src/components` — research setup, progress, Cytoscape graph, filters, paper panel и table.
- `frontend/src/app` — Next.js App Router shell и адаптивные стили.

## Быстрая настройка

Требуется Python 3.12, `uv`, Node.js 20.9 или новее, Docker и Docker Compose.

```powershell
if (-not (Test-Path .env)) { Copy-Item example.env .env }
uv sync --dev
npm.cmd --prefix frontend install
docker compose config --quiet
```

При первом запуске worker скачивает модель из `EMBEDDING_MODEL_NAME`. По умолчанию используется
готовая Sentence Transformers-модель `sentence-transformers/allenai-specter` с размерностью 768;
имя, версия cache contract и batch size задаются в
`.env`. Изменение размерности требует отдельной миграции колонки `VECTOR(768)`.

`SEMANTIC_SCHOLAR_API_KEY` необязателен, но рекомендуется из-за rate limits. Secrets
не должны попадать в repository. PostgreSQL публикуется на локальном порту `55432`,
чтобы не конфликтовать с системной установкой PostgreSQL на стандартном `5432`.

## Локальный запуск

Сначала поднимите stateful dependencies и примените миграцию:

```powershell
docker compose up -d postgres redis
uv run alembic -c backend/alembic.ini upgrade head
```

PostgreSQL запускается из pinned-образа `pgvector/pgvector`, а миграция включает расширение
`vector` и создаёт таблицы `paper_embeddings` и `project_paper_question_scores`.

API и worker можно запустить локально в отдельных терминалах:

```powershell
$env:PYTHONPATH = "backend"
uv run uvicorn app.main:app --reload
```

```powershell
$env:PYTHONPATH = "backend"
uv run python -m app.workers.research_worker
```

Frontend запускается в третьем терминале:

```powershell
Set-Location frontend
npm.cmd run dev
```

## Запуск через Docker Compose

Собрать образы, применить миграции из container environment и запустить полный стек:

```powershell
docker compose build
docker compose up -d postgres redis
docker compose run --rm api alembic -c backend/alembic.ini upgrade head
docker compose up -d api worker frontend
docker compose ps
```

API не применяет Alembic migrations автоматически. Команду `upgrade head` необходимо выполнять
перед первым запуском и после появления новой migration revision.

Health endpoints:

- `GET http://localhost:8000/health/live` — состояние API process.
- `GET http://localhost:8000/health/ready` — PostgreSQL и Redis connections.

## REST API

Основной workflow:

```text
POST /projects
POST /projects/{project_id}/questions
POST /projects/{project_id}/related-work
POST /projects/{project_id}/research
GET  /research/{job_id}
```

Persisted results без повторного запуска pipeline:

```text
GET /projects/{project_id}/papers
GET /projects/{project_id}/papers/{paper_id}
GET /projects/{project_id}/ranking
GET /projects/{project_id}/graph
```

`papers`, `ranking` и `graph` поддерживают filters по topic/final score, year, citations,
depth, category и seed status. Upload использует `multipart/form-data`, поле файла — `file`.

## Frontend

Для локального запуска сначала запустите API и worker, затем откройте отдельный терминал:

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

Приложение доступно на `http://localhost:3000`, API по умолчанию ожидается на
`http://localhost:8000`. Другой адрес задаётся через `NEXT_PUBLIC_API_BASE_URL` до frontend build.
Browser origin для CORS задаётся backend-переменной `FRONTEND_ORIGIN`.

После завершения job frontend одновременно загружает ranking и citation graph. Graph filters по
score, year, citations, depth, category и seed status обновляют graph и ranked table через persisted
API results. Hover выделяет ближайшее citation neighborhood, а клик по node или table paper загружает
paper details и question-level relevance без повторного запуска research pipeline.

Полный Docker Compose включает frontend, API, worker, PostgreSQL и Redis. Подробная
последовательность запуска, health checks и диагностика приведены в
[`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Проверка

Тесты не обращаются к live Semantic Scholar API: resolver/discovery используют DTO
fixtures и mocks, parser проверяется на реальном `data/related_work_matrix.xlsx`, а
repositories и pipeline используют изолированную in-memory database.

Тесты не загружают реальную embedding-модель и не обращаются к live graph service: inference
использует детерминированные mocks, а NetworkX анализирует локальные fixture-графы.
API fixture использует in-memory database и mock Redis, поэтому не запускает worker.

```powershell
uv run pytest
```

```powershell
uv run ruff check backend tests
uv run ruff format --check backend tests
```

Frontend проверяется отдельно после `npm install`:

```powershell
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```

Сквозной Docker Compose acceptance flow, проверка persistence, фильтров без повторного research
job и error-handling smoke tests описаны в [`docs/RUNBOOK.md`](docs/RUNBOOK.md#6-сквозной-api-acceptance-flow).
