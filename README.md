# Scientific Research Graph

Scientific Research Graph — приложение для поиска и анализа научных публикаций вокруг заданной
области исследования. Пользователь загружает матрицу Related Work, формулирует исследовательские
вопросы, а система находит исходные статьи в Semantic Scholar, исследует многоуровневые связи в
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
ResearchPipeline сначала разрешает seeds, сохраняет их глобальные metadata и создаёт либо читает
versioned seed embeddings. Затем citation discovery выполняется bounded breadth-first traversal:
seeds находятся на depth `0`, каждый следующий frontier формируется preliminary semantic
component и сбалансированным per-question selector до `max_depth`, `max_papers` или пустого
frontier. Только выбранный induced graph получает project membership, после чего без изменения
публичного API выполняются прежние semantic, impact, graph и final ranking stages.

## Документация

- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — настройка окружения, локальный и Docker Compose запуск,
  миграции, автоматические проверки, acceptance flow и диагностика.
- [`docs/SCORING.md`](docs/SCORING.md) — назначение метрик, формулы, веса, missing-value policy
  и пример расчёта статьи.
- [`docs/ARCHITECTURE_DECISIONS.md`](docs/ARCHITECTURE_DECISIONS.md) — принятые архитектурные
  решения, включая разделение preliminary и final semantic scoring.
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

Discovery ranking выполняется до включения кандидата в project graph. Для каждой пары
`candidate × research question` он использует только semantic similarity к вопросу и ближайшей
seed paper. Citations, год публикации, PageRank и другие final-ranking signals на этот отбор не
влияют. Каждый вопрос получает отдельный ranked shortlist, а versioned paper embeddings повторно
используются из PostgreSQL/pgvector между проектами. Balanced selector сначала выбирает по одному
уникальному кандидату для каждого вопроса, затем заполняет оставшийся глобальный лимит по
максимальному preliminary score. Общие papers дедуплицируются, а равные scores упорядочиваются по
canonical paper ID, поэтому повторный запуск на одинаковом входе даёт тот же результат.

На каждом уровне citations запрашиваются для всех papers текущего frontier. References всегда
запрашиваются для seeds, а для discovered papers — только когда их лучший preliminary score не
ниже `expand_references_topic_threshold`. Кандидаты дедуплицируются до embeddings, `max_papers`
включает seeds, а в project graph сохраняются только выбранные papers и рёбра между ними. Ошибка
одного provider request фиксируется отдельно и не останавливает остальные ветви обхода.

## Архитектура текущего этапа

- `backend/app/api` — только HTTP и health checks.
- `backend/app/domain` — framework-independent глобальные и project-specific модели.
- `backend/app/research` — discovery, embeddings, semantic, graph, impact и final ranking.
- `backend/app/providers` — Semantic Scholar HTTP adapter.
- `backend/app/repositories` — graph, embedding, score и ResearchJob persistence.
- `backend/app/application` — создание job и постановка в Redis queue.
- `backend/app/infrastructure` — PostgreSQL и Redis adapters.
- `backend/app/infrastructure/document_storage.py` — единый local/S3-compatible contract для PDF.
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

Document storage выбирается через `DOCUMENT_STORAGE_BACKEND`: `local` хранит PDF в
`DOCUMENT_STORAGE_LOCAL_ROOT`, а `s3` использует S3-compatible bucket. API и worker в Docker
Compose совместно монтируют local volume. Для production S3 endpoint можно не задавать и
использовать стандартную AWS credential chain; static credentials передаются только через
environment и не сохраняются в repository. Максимальный PDF ограничен
`DOCUMENT_STORAGE_MAX_BYTES` до любой записи. Service-integration contract S3 adapter проверяется
на реальном RustFS container из отдельного Compose profile.

После завершения metadata pipeline worker получает PDF только из arXiv. HTTP-клиент следует
redirect, ограничивает timeout/число retry/размер и проверяет `Content-Type`, `%PDF-` и SHA-256 до
записи. Production deployment должен заменить контакт в `ARXIV_USER_AGENT` на действительный.

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
GET /projects/{project_id}/documents
POST /projects/{project_id}/papers/{paper_id}/document
```

`papers`, `ranking` и `graph` поддерживают filters по topic/final score, year, citations,
depth, category и seed status. Upload использует `multipart/form-data`, поле файла — `file`.

Конфигурация проекта принимает следующие параметры discovery и подготовки PDF:

| Поле | Default | Семантика |
|---|---:|---|
| `max_depth` | `2` | Число уровней citation discovery, допустимо `1–5` |
| `max_papers` | `300` | Жёсткий лимит всех project papers, включая seeds |
| `top_k_expansion` | `20` | Глобальный лимит выбранных статей одного уровня |
| `expand_references_topic_threshold` | `0.75` | Минимальный preliminary score для раскрытия references discovered paper |
| `pdf_top_n` | `20` | Число discovered PDF targets; seeds в лимит не входят |
| `allow_manual_pdf_upload` | `false` | Разрешает manual fallback для недоступных arXiv PDF |

После добавления вопросов `top_k_expansion` должен быть не меньше их общего числа. Это позволяет
последующему сбалансированному selector представить каждый research question. Старые проекты, в
JSON-конфигурации которых новых полей нет, получают указанные defaults при чтении.

## ResearchJob и DocumentJob

`ResearchJob` отвечает только за разрешение seeds, citation discovery, metadata embeddings и
итоговый ranking. После ranking он идемпотентно создаёт PDF targets: все seeds и не более
`pdf_top_n` discovered papers, сбалансированных по research questions. После создания targets
`ResearchJob` переходит в `COMPLETED` и не ожидает загрузку или ручной upload PDF.

После этого worker независимо обрабатывает targets. Успешный arXiv download или разрешённый
multipart upload переводит document job в `PARSING`. Если canonical arXiv ID/PDF отсутствует,
получается `UNAVAILABLE` при выключенном fallback или `AWAITING_UPLOAD` при включённом. Upload API
принимает файл только для точной пары project/paper в `AWAITING_UPLOAD`; frontend показывает control
только в этом состоянии и только при `allow_manual_pdf_upload=true`.

Каждый target получает отдельный `DocumentProcessingJob`. Его lifecycle охватывает получение PDF,
GROBID parsing, chunking и indexing; состояния `AWAITING_UPLOAD`, `UNAVAILABLE` и `FAILED` относятся
только к конкретному документу. PDF, исходный TEI, нормализованные элементы и chunks имеют
независимые version contracts. Подробная ownership-модель и state machine описаны в
[`docs/DOCUMENT_PIPELINE.md`](docs/DOCUMENT_PIPELINE.md).

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

Default-тесты не обращаются к live Semantic Scholar API: discovery использует записанный
fixture-provider, parser проверяется на реальном `data/related_work_matrix.xlsx`, а
repositories и pipeline используют изолированную in-memory database.

Тесты не загружают реальную embedding-модель и не обращаются к live graph service: inference
использует детерминированные mocks, а NetworkX анализирует локальные fixture-графы.
API fixture использует in-memory database и mock Redis, поэтому не запускает worker.

```powershell
uv run pytest -m "not service_integration and not external"
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
