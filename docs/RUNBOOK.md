# Scientific Research Graph — Runbook

Документ описывает настройку, локальный и контейнерный запуск, миграции, тестирование,
сквозную acceptance-проверку и диагностику системы.

Все команды рассчитаны на PowerShell и выполняются из корня репозитория, если явно не
указана другая рабочая директория.

## 1. Требования

- Python 3.12.
- `uv`.
- Node.js 20.9 или новее.
- Docker Engine и Docker Compose.
- Свободные порты `3000`, `6379`, `8000` и `55432`.

Проверка инструментов:

```powershell
python --version
uv --version
node --version
npm.cmd --version
docker version
docker compose version
```

Проверка занятых портов:

```powershell
Get-NetTCPConnection `
    -LocalPort 3000,6379,8000,55432 `
    -State Listen `
    -ErrorAction SilentlyContinue
```

## 2. Первоначальная настройка

Создать локальный файл окружения, не перезаписывая существующий:

```powershell
if (-not (Test-Path .env)) {
    Copy-Item example.env .env
}
```

Основные значения по умолчанию:

```dotenv
FRONTEND_ORIGIN=http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
DATABASE_URL=postgresql+psycopg://research:research@127.0.0.1:55432/research_graph
POSTGRES_PORT=55432
REDIS_URL=redis://localhost:6379/0
WORKER_QUEUE_NAME=research_jobs
```

`SEMANTIC_SCHOLAR_API_KEY` необязателен, но рекомендуется из-за rate limits. Секрет
должен храниться только в `.env` и не должен попадать в Git.

Проверить наличие ключа, не выводя его значение:

```powershell
$keyConfigured = [bool](
    Get-Content .env |
    Where-Object { $_ -match '^SEMANTIC_SCHOLAR_API_KEY=.+$' }
)

Write-Host "Semantic Scholar API key configured: $keyConfigured"
```

Установить Python-зависимости:

```powershell
uv sync --dev
```

Установить frontend-зависимости:

```powershell
npm.cmd --prefix frontend install
```

Проверить Compose-конфигурацию без вывода resolved secrets:

```powershell
docker compose config --quiet
```

## 3. Локальный запуск для разработки

В этом режиме PostgreSQL и Redis работают в Docker, а API, worker и frontend запускаются
локально с автоматической перезагрузкой frontend/backend кода.

### 3.1. PostgreSQL и Redis

```powershell
docker compose up -d postgres redis
docker compose ps
```

Проверить инфраструктуру:

```powershell
docker compose exec -T postgres pg_isready -U research -d research_graph
docker compose exec -T redis redis-cli ping
```

Ожидаются `accepting connections` и `PONG`.

### 3.2. Миграции

```powershell
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini current
```

### 3.3. API

Открыть отдельный PowerShell-терминал из корня репозитория:

```powershell
$env:PYTHONPATH = "backend"
uv run uvicorn app.main:app --reload
```

API будет доступен на `http://localhost:8000`.

### 3.4. Worker

Открыть второй PowerShell-терминал из корня репозитория:

```powershell
$env:PYTHONPATH = "backend"
uv run python -m app.workers.research_worker
```

Первый запуск может занять больше времени из-за загрузки embedding-модели.

### 3.5. Frontend

Открыть третий PowerShell-терминал:

```powershell
Set-Location frontend
npm.cmd run dev
```

Frontend будет доступен на `http://localhost:3000`.

### 3.6. Health checks

```powershell
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready

$frontendResponse = Invoke-WebRequest http://localhost:3000
$frontendResponse.StatusCode
```

Frontend должен вернуть HTTP `200`.

## 4. Полный запуск через Docker Compose

### 4.1. Сборка образов

```powershell
docker compose build --pull
```

### 4.2. Запуск инфраструктуры и миграции

API не применяет миграции автоматически. Перед первым полным запуском или после появления
новой migration revision выполнить:

```powershell
docker compose up -d postgres redis
docker compose run --rm api alembic -c backend/alembic.ini upgrade head
docker compose run --rm api alembic -c backend/alembic.ini current
```

### 4.3. Запуск всех сервисов

```powershell
docker compose up -d api worker frontend
docker compose ps
```

Проверка сервисов:

```powershell
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready

$frontendResponse = Invoke-WebRequest http://localhost:3000
$frontendResponse.StatusCode
```

Стартовые логи:

```powershell
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
docker compose logs --tail=100 frontend
```

Непрерывный просмотр worker logs:

```powershell
docker compose logs --follow worker
```

`Ctrl+C` прекращает только просмотр логов, а не работу контейнера.

## 5. Автоматические проверки

### 5.1. Backend

Обычный набор backend-тестов использует SQLite in-memory и test doubles на внешних
границах. Запущенные PostgreSQL, Redis, worker и доступ в интернет для него не нужны:

```powershell
uv run pytest -m "not service_integration and not external"
```

Service integration и external tests в этот прогон не входят. Тест Semantic Scholar защищён
`skipif` и без явного opt-in отображается как `SKIPPED`.

Запуск отдельных групп:

```powershell
uv run pytest tests/backend/test_api.py -q
uv run pytest tests/backend/test_discovery.py -q
uv run pytest tests/backend/test_research_pipeline.py -q
uv run pytest tests/backend/test_seed_resolution.py -q
uv run pytest tests/backend/test_project_config.py -m "not service_integration" -q
npm.cmd --prefix frontend test -- research-form.test.ts research-api.test.ts
```

#### 5.1.1. Многоуровневый citation traversal

Targeted suite использует настоящий `CitationDiscovery`, записанный fixture-provider и проверяет
depth `1/2/3/5`, циклы, раннюю остановку, hard limits, threshold references и изоляцию ошибок:

```powershell
python --version
uv --version
uv sync --dev
uv run pytest --version
uv run ruff --version
uv run pytest tests/backend/test_discovery.py tests/backend/test_research_pipeline.py -v
```

Безопасная стартовая конфигурация для ручной проверки — `max_depth=2`, `max_papers=50` и
`top_k_expansion=10`. Рост `max_depth`, размера frontier и числа seeds увеличивает число запросов;
для live API рекомендуется задать `SEMANTIC_SCHOLAR_API_KEY` и сначала использовать малые лимиты.
External smoke test выполняется отдельно и никогда не заменяет deterministic suite:

```powershell
$env:RUN_EXTERNAL_RESEARCH_TESTS = "1"
uv run pytest tests/backend/test_semantic_scholar_integration.py -m external -v
Remove-Item Env:RUN_EXTERNAL_RESEARCH_TESTS
```

Без `SEMANTIC_SCHOLAR_API_KEY` Graph API применяет общий неаутентифицированный rate limit и может
ответить `429` уже на первом запросе. Такой результат означает недоступность внешнего gate, а не
успех или дефект traversal. Для воспроизводимой проверки задайте ключ в `.env`, не добавляя файл
в Git; тест намеренно не превращает `429` в skip или pass.

Проверка промежуточных состояний и отказов pipeline:

```powershell
uv run pytest tests/backend/test_research_pipeline.py -v
```

Эта группа проверяет последовательность `RESOLVING_SEEDS` → `DISCOVERING` → `EMBEDDING` →
`SCORING` → `GRAPH_ANALYSIS` → `COMPLETED`, а также переход в `FAILED` при сбое разрешения
seed papers и при полном отказе embedding backend.

#### 5.1.2. Интеграция traversal в ResearchPipeline

Default targeted tests проверяют порядок seed embeddings → discovery, depth `2`, минимальную
persisted depth, монотонный progress и повторный job без duplicates:

```powershell
python --version
uv --version
uv sync --dev
uv run pytest --version
uv run ruff --version
uv run pytest tests/backend/test_research_pipeline.py tests/backend/test_repositories.py -v
```

Основной gate этапа 5 использует настоящие PostgreSQL/pgvector и Redis. Проверить Docker и
подготовить services:

```powershell
docker version
docker compose version
docker compose config --quiet
docker compose up -d postgres redis
docker compose ps postgres redis
docker compose exec -T postgres pg_isready -U research -d research_graph
docker compose exec -T redis redis-cli ping
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini current
```

После ответов `accepting connections`, `PONG` и актуальной Alembic revision запустить service
integration. Тест создаёт уникальные project/queue данные и удаляет их в `finally`:

```powershell
uv run pytest tests/backend/test_research_pipeline_integration.py -m service_integration -v
```

Ручной acceptance с `max_depth=2` выполняется через обычный UI/API и worker. Во время job значение
`progress` не должно уменьшаться; ranking и graph endpoints после `COMPLETED` должны возвращать
одинаковый набор paper IDs, рёбра только между выбранными nodes и depths `0..2`.

#### 5.1.3. Preliminary semantic scoring

Быстрые targeted tests проверяют подготовку `title`/`title [SEP] abstract`, controlled vectors,
missing-value policy, сортировку, независимые shortlists и повторное использование cache:

```powershell
uv run pytest tests/backend/test_embeddings.py tests/backend/test_preliminary_scoring.py -q
```

Для реальной SPECTER → pgvector цепочки сначала проверить окружение и подготовить PostgreSQL:

```powershell
python --version
uv --version
docker version
docker compose version
uv sync --dev
docker compose up -d postgres
docker compose exec -T postgres pg_isready -U research -d research_graph
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini current
```

Затем запустить integration test:

```powershell
uv run pytest tests/backend/test_preliminary_scoring_integration.py -m service_integration -v
```

Первый запуск загружает `sentence-transformers/allenai-specter` и может быть заметно дольше.
Последующие запуски используют локальный Hugging Face cache. Для первого запуска нужен доступ к
модели; `EMBEDDING_MODEL_NAME`, `EMBEDDING_MODEL_VERSION` и `EMBEDDING_DIMENSIONS` должны
соответствовать применённой pgvector migration.

#### 5.1.4. Balanced per-question selector

Selector не использует внешние сервисы, БД или дополнительные зависимости. Проверить базовое
окружение и наличие установленной dev-группы:

```powershell
python --version
uv --version
uv sync --dev
uv run pytest --version
uv run ruff --version
```

Запустить targeted tests этапа 3:

```powershell
uv run pytest tests/backend/test_balanced_selection.py -v
```

Проверки покрывают один и несколько вопросов, пересекающиеся shortlists, глобальный лимит,
представительство при точном лимите, canonical tie-breaker и повторяемость результата.

#### 5.1.5. PostgreSQL config acceptance

Проверить, что локальный PostgreSQL готов и migrations применены, затем выполнить реальный
round-trip конфигурации через API/repository:

```powershell
docker compose up -d postgres
docker compose exec -T postgres pg_isready -U research -d research_graph
uv run alembic -c backend/alembic.ini upgrade head
uv run pytest tests/backend/test_project_config.py -m service_integration -v
```

Тест создаёт уникальный проект и удаляет его в `finally`. In-memory database в этом профиле не
используется.

#### 5.1.6. Live Semantic Scholar API

Live-тест выполняет реальный HTTP-запрос и по умолчанию пропускается. Разрешить его только
для текущей PowerShell-сессии и запустить отдельно:

```powershell
$env:RUN_EXTERNAL_RESEARCH_TESTS = "1"
uv run pytest tests/backend/test_semantic_scholar_integration.py -v -m external
```

`SEMANTIC_SCHOLAR_API_KEY` необязателен, но рекомендуется из-за публичных rate limits.
`Settings` читает ключ из `.env`; выводить ключ в команду или сохранять его в Git не нужно.

После проверки удалить только временный opt-in флаг:

```powershell
Remove-Item Env:RUN_EXTERNAL_RESEARCH_TESTS -ErrorAction SilentlyContinue
```

Если API key был задан вручную в текущем терминале, а не загружен из `.env`, удалить и его:

```powershell
Remove-Item Env:SEMANTIC_SCHOLAR_API_KEY -ErrorAction SilentlyContinue
```

Постоянно менять `.env`, `pyproject.toml` или конфигурацию приложения после live-теста не
требуется. Ответы `429`, `5xx` и transport timeout означают проблему внешнего сервиса или
rate limit, а не обязательную ошибку локального кода.

#### 5.1.7. Статический анализ и форматирование

```powershell
uv run ruff check backend tests
uv run ruff format --check backend tests
```

Исправить только форматирование:

```powershell
uv run ruff format backend tests
```

После автоматического форматирования повторно выполнить `ruff check` и tests.

### 5.2. Frontend

```powershell
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```

Успешная проверка должна завершиться без ESLint и TypeScript errors, с пройденными Vitest
tests и успешным production build.

## 6. Сквозной API acceptance flow

Перед выполнением должны работать `postgres`, `redis`, `api` и `worker`, а миграции должны
быть применены.

### 6.1. Создание проекта и запуск job

Выполнить следующий блок из корня репозитория:

```powershell
$apiBase = "http://localhost:8000"
$rootPath = (Get-Location).Path

$projectPayload = @{
    name = "Docker Compose acceptance"
    config = @{
        max_depth = 1
        max_papers = 30
        top_k_expansion = 5
        expand_references_topic_threshold = 0.75
        pdf_top_n = 10
        allow_manual_pdf_upload = $false
    }
} | ConvertTo-Json -Depth 4

$project = Invoke-RestMethod `
    -Uri "$apiBase/projects" `
    -Method Post `
    -ContentType "application/json" `
    -Body $projectPayload

$projectId = $project.id
Write-Host "Project ID: $projectId"

$savedProject = Invoke-RestMethod -Uri "$apiBase/projects/$projectId" -Method Get
if ($savedProject.config.max_depth -ne 1 `
    -or $savedProject.config.pdf_top_n -ne 10 `
    -or $savedProject.config.allow_manual_pdf_upload -ne $false) {
    throw "Saved project configuration differs from the create payload"
}

$questionsPayload = @{
    questions = @(
        "How can citation graphs improve scientific literature discovery?"
    )
} | ConvertTo-Json -Depth 3

$questions = Invoke-RestMethod `
    -Uri "$apiBase/projects/$projectId/questions" `
    -Method Post `
    -ContentType "application/json" `
    -Body $questionsPayload

Write-Host "Questions created: $($questions.questions.Count)"

$relatedWorkPath = Join-Path $rootPath "data\related_work_matrix.xlsx"

$uploadRaw = curl.exe `
    --silent `
    --show-error `
    --fail-with-body `
    --request POST `
    --form "file=@$relatedWorkPath" `
    "$apiBase/projects/$projectId/related-work"

if ($LASTEXITCODE -ne 0) {
    throw "Related Work upload failed"
}

$upload = ($uploadRaw -join "`n") | ConvertFrom-Json
Write-Host "Related Work entries: $($upload.entries_count)"

$job = Invoke-RestMethod `
    -Uri "$apiBase/projects/$projectId/research" `
    -Method Post

$jobId = $job.id
Write-Host "Research job ID: $jobId"
```

### 6.2. Ожидание завершения job

```powershell
$deadline = (Get-Date).AddMinutes(30)

do {
    $job = Invoke-RestMethod "$apiBase/research/$jobId"

    Write-Host (
        "Status={0}; progress={1}; discovered={2}; processed={3}" -f `
        $job.status,
        $job.progress,
        $job.papers_discovered,
        $job.papers_processed
    )

    if ($job.status -in @("COMPLETED", "FAILED")) {
        break
    }

    if ((Get-Date) -gt $deadline) {
        throw "Research job timeout after 30 minutes"
    }

    Start-Sleep -Seconds 3
} while ($true)

if ($job.status -eq "FAILED") {
    throw "Research failed: $($job.error_message)"
}
```

### 6.3. Проверка сохранённых результатов

```powershell
$papers = Invoke-RestMethod "$apiBase/projects/$projectId/papers"
$ranking = Invoke-RestMethod "$apiBase/projects/$projectId/ranking"
$graph = Invoke-RestMethod "$apiBase/projects/$projectId/graph"

Write-Host "Papers: $($papers.count)"
Write-Host "Ranking: $($ranking.count)"
Write-Host "Graph nodes: $($graph.nodes.Count)"
Write-Host "Graph edges: $($graph.edges.Count)"

if ($ranking.count -lt 1) {
    throw "Completed job returned an empty ranking"
}

$paperId = $ranking.papers[0].paper_id
$details = Invoke-RestMethod "$apiBase/projects/$projectId/papers/$paperId"

$details.paper |
    Select-Object title,year,citation_count,is_seed,depth,final_score

$details.question_scores | Format-Table
```

### 6.4. Проверка фильтров без нового research job

```powershell
$jobsBefore = [int]((
    docker compose exec -T postgres psql `
        -U research `
        -d research_graph `
        -tAc "SELECT COUNT(*) FROM research_jobs;"
) | Out-String).Trim()

$filteredRanking = Invoke-RestMethod `
    "$apiBase/projects/$projectId/ranking?min_final_score=0&max_depth=1&is_seed=false"

$filteredGraph = Invoke-RestMethod `
    "$apiBase/projects/$projectId/graph?min_final_score=0&max_depth=1&is_seed=false"

$jobsAfter = [int]((
    docker compose exec -T postgres psql `
        -U research `
        -d research_graph `
        -tAc "SELECT COUNT(*) FROM research_jobs;"
) | Out-String).Trim()

Write-Host "Filtered ranking: $($filteredRanking.count)"
Write-Host "Filtered nodes: $($filteredGraph.nodes.Count)"
Write-Host "Jobs before filters: $jobsBefore"
Write-Host "Jobs after filters:  $jobsAfter"

if ($jobsBefore -ne $jobsAfter) {
    throw "Filters unexpectedly created a new research job"
}
```

## 7. Frontend acceptance

Открыть приложение:

```powershell
Start-Process "http://localhost:3000"
```

Проверить вручную:

1. Создание проекта с `max_depth=5`, новым threshold/PDF limit и выключенным manual upload.
2. Повторное открытие `GET /projects/{project_id}` в DevTools Network и совпадение config с формой.
3. Сообщение валидации при `top_k_expansion` меньше числа строк research questions.
4. Загрузку `data/related_work_matrix.xlsx`.
5. Обновление progress до `COMPLETED`.
6. Появление ranking и citation graph.
7. Hover по node и выделение citation neighborhood.
8. Выбор paper из graph и table.
9. Отображение metadata, component scores и question relevance.
10. Синхронную фильтрацию graph и ranking без нового job.
11. Empty state для слишком строгих filters.
12. Адаптивную раскладку на узком экране.

## 8. Persistence и hardening checks

### 8.1. Сохранность после перезапуска

Команды используют `$apiBase` и `$projectId` из acceptance flow:

```powershell
docker compose restart api worker frontend
Start-Sleep -Seconds 8

Invoke-RestMethod http://localhost:8000/health/ready

$persistedProject = Invoke-RestMethod "$apiBase/projects/$projectId"
$persistedRanking = Invoke-RestMethod "$apiBase/projects/$projectId/ranking"

Write-Host "Persisted project: $($persistedProject.name)"
Write-Host "Persisted papers: $($persistedRanking.count)"
```

### 8.2. Error-handling smoke tests

Несуществующий project должен вернуть `404`:

```powershell
curl.exe `
    --silent `
    --output NUL `
    --write-out "Missing project HTTP %{http_code}\n" `
    "$apiBase/projects/00000000-0000-0000-0000-000000000000"
```

Некорректный project payload должен вернуть `422`:

```powershell
curl.exe `
    --silent `
    --output NUL `
    --write-out "Invalid project HTTP %{http_code}\n" `
    --request POST `
    --header "Content-Type: application/json" `
    --data '{"name":"","config":{}}' `
    "$apiBase/projects"
```

Неподдерживаемый upload должен вернуть `422`:

```powershell
curl.exe `
    --silent `
    --output NUL `
    --write-out "Invalid upload HTTP %{http_code}\n" `
    --request POST `
    --form "file=@$rootPath\pyproject.toml" `
    "$apiBase/projects/$projectId/related-work"
```

### 8.3. Runtime и database diagnostics

```powershell
docker compose ps
docker stats --no-stream

docker compose logs --since=30m api worker frontend |
    Select-String -Pattern "Traceback|ERROR|Unhandled|Exception"
```

Если `Select-String` ничего не выводит, указанные критические шаблоны в логах не найдены.

Проверка job statuses и основных таблиц:

```powershell
docker compose exec -T postgres psql `
    -U research `
    -d research_graph `
    -c "SELECT status, COUNT(*) FROM research_jobs GROUP BY status ORDER BY status;"

docker compose exec -T postgres psql `
    -U research `
    -d research_graph `
    -c "SELECT COUNT(*) AS projects FROM research_projects; SELECT COUNT(*) AS papers FROM papers; SELECT COUNT(*) AS citations FROM citations;"
```

### 8.4. DocumentStorage и RustFS

Local backend используется по умолчанию:

```powershell
$env:DOCUMENT_STORAGE_BACKEND = "local"
$env:DOCUMENT_STORAGE_LOCAL_ROOT = ".\data\document-storage"
$env:DOCUMENT_STORAGE_MAX_BYTES = "50000000"
```

Для production S3 задайте `DOCUMENT_STORAGE_BACKEND=s3`, bucket и region. Оставьте
`DOCUMENT_STORAGE_S3_ENDPOINT_URL` пустым для AWS S3 или укажите URL совместимого сервиса.
Credentials не записываются в `.env` под version control: используйте environment, secret store
или стандартную AWS credential chain.

Проверка RustFS-контракта выполняется отдельным Compose profile. Сначала проверить окружение:

```powershell
uv run python -c "import boto3; print(boto3.__version__)"
docker version
docker compose version
docker compose config --quiet
```

Если `boto3` отсутствует, синхронизировать уже объявленные зависимости:

```powershell
uv sync --dev
```

Поднять RustFS и убедиться, что healthcheck успешен:

```powershell
docker pull rustfs/rustfs:1.0.0
docker compose --profile service-integration up -d rustfs
docker compose --profile service-integration ps rustfs
Invoke-RestMethod http://127.0.0.1:59000/health
```

Targeted gate этапа 7:

```powershell
uv run pytest -m "not service_integration and not external" tests/backend/test_document_storage.py
uv run pytest -m service_integration tests/backend/test_document_storage.py
```

После targeted gate выполняется общий gate из раздела 5. RustFS использует тот же S3-compatible
contract, что production; тест самостоятельно идемпотентно создаёт test bucket.

### 8.5. arXiv download и manual upload

Проверить настройки и уже объявленные зависимости этапа 8:

```powershell
uv run python -c "import httpx, multipart; print(httpx.__version__)"
$env:ARXIV_PDF_BASE_URL = "https://export.arxiv.org/pdf"
$env:ARXIV_DOWNLOAD_TIMEOUT_SECONDS = "30"
$env:ARXIV_DOWNLOAD_MAX_RETRIES = "3"
$env:ARXIV_USER_AGENT = "ResearchPapersPet/0.1 (mailto:your-real-contact@example.com)"
```

Если импорт не работает, синхронизировать существующий lockfile (новые пакеты этапу 8 не нужны):

```powershell
uv sync --dev
```

После завершения research job получить document states:

```powershell
$documents = Invoke-RestMethod `
    -Uri "http://localhost:8000/projects/$projectId/documents"
$documents.documents | Format-Table paper_id, status, source, error_message
```

Для target в `AWAITING_UPLOAD` загрузить PDF. Endpoint отклонит запрос, если checkbox проекта был
выключен, paper не является выбранным target или состояние уже изменилось:

```powershell
curl.exe -f -X POST `
    -F "file=@C:\path\to\paper.pdf;type=application/pdf" `
    "http://localhost:8000/projects/$projectId/papers/$paperId/document"
```

Targeted local gate этапа 8 использует настоящий loopback HTTP server и настоящий multipart/local
storage path, но не обращается в интернет:

```powershell
uv run pytest -m "not external" `
    tests/backend/test_arxiv_documents.py `
    tests/backend/test_document_upload_api.py `
    tests/backend/test_research_pipeline.py
npm.cmd --prefix frontend test -- paper-panel-document.test.ts research-api.test.ts
```

External arXiv gate запускается отдельно и осознанно:

```powershell
$env:RUN_EXTERNAL_RESEARCH_TESTS = "1"
uv run pytest -m external tests/backend/test_arxiv_documents.py
Remove-Item Env:RUN_EXTERNAL_RESEARCH_TESTS
```

После targeted/external checks выполнить полный gate из раздела 5 и сообщить число skipped tests.

## 9. Диагностика проблем

### Document statuses

Research job не ожидает document pipeline. После `COMPLETED` проверить созданные PDF targets и их
независимые состояния можно в PostgreSQL:

```powershell
docker compose exec -T postgres psql `
    -U research `
    -d research_graph `
    -c "SELECT project_id, paper_id, source, status, error_message, created_at FROM document_processing_jobs ORDER BY created_at DESC;"
```

Связанные версии PDF и parser results:

```powershell
docker compose exec -T postgres psql `
    -U research `
    -d research_graph `
    -c "SELECT paper_id, source, version, status, is_active, checksum FROM paper_documents ORDER BY paper_id, source, version; SELECT document_id, parser_name, parser_version, error_message FROM parsed_documents ORDER BY created_at DESC;"
```

Targeted gate этапа 6 выполняется после применения migration:

```powershell
uv run alembic -c backend/alembic.ini upgrade head
uv run pytest tests/backend/test_documents.py tests/backend/test_research_pipeline.py
uv run pytest -m service_integration tests/backend/test_documents_integration.py
```

Migration integration test создаёт отдельную UUID-схему PostgreSQL, выполняет upgrade с
`20260825_0002` до `head` и удаляет только эту временную схему.

### Сервис не запустился

```powershell
docker compose ps -a
docker compose logs --tail=200 api worker frontend postgres redis
```

### API live, но readiness возвращает ошибку

```powershell
docker compose exec -T postgres pg_isready -U research -d research_graph
docker compose exec -T redis redis-cli ping
docker compose logs --tail=200 api postgres redis
```

### Worker не забирает job

```powershell
docker compose logs --tail=200 worker
docker compose exec -T redis redis-cli LLEN research_jobs
```

Проверить, что `WORKER_QUEUE_NAME` в `.env` равен `research_jobs` и одинаков для API и worker.

### Ошибка схемы database

```powershell
docker compose run --rm api alembic -c backend/alembic.ini current
docker compose run --rm api alembic -c backend/alembic.ini upgrade head
```

### Semantic Scholar rate limit или provider timeout

```powershell
docker compose logs --tail=300 worker |
    Select-String -Pattern "Semantic Scholar|429|timeout|retry"
```

Добавить API key в `.env`, затем пересоздать процессы, использующие environment:

```powershell
docker compose up -d --force-recreate api worker
```

### Проверка локальных переменных без вывода API key

```powershell
Get-Content .env |
    Where-Object { $_ -notmatch '^SEMANTIC_SCHOLAR_API_KEY=' }
```

## 10. Остановка и очистка

Остановить локально запущенные API, worker и frontend через `Ctrl+C`, затем остановить Docker
services с сохранением PostgreSQL volume:

```powershell
docker compose down
```

Остановить сервисы без удаления контейнеров:

```powershell
docker compose stop
```

Полностью удалить контейнеры и PostgreSQL volume:

```powershell
docker compose down --volumes
```

Команда с `--volumes` безвозвратно удаляет данные PostgreSQL и предназначена только для
намеренного полного сброса локального окружения.
