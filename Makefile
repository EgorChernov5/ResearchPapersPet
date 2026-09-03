COMPOSE := docker compose

.PHONY: start build rebuild stop ensure-env

# Использует готовые образы, применяет миграции и запускает полный стек.
start: ensure-env
	$(COMPOSE) config --quiet
	$(COMPOSE) up -d postgres redis
	$(COMPOSE) run --rm api alembic -c backend/alembic.ini upgrade head
	$(COMPOSE) up -d api worker frontend
	$(COMPOSE) ps

# Собирает образы с повторным использованием Docker и package-manager caches.
build: ensure-env
	$(COMPOSE) config --quiet
	$(COMPOSE) build

# Пересобирает изменившиеся образы и запускает приложение.
rebuild: build start

# Останавливает сервисы, сохраняя контейнеры и данные PostgreSQL.
stop:
	$(COMPOSE) stop

# Создаёт локальное окружение из шаблона только при отсутствии .env.
ensure-env:
	powershell.exe -NoProfile -Command "if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath 'example.env' -Destination '.env'; Write-Host 'Created .env from example.env' }"
