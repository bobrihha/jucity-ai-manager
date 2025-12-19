# jucity-ai-manager — MVP-0 (Facts-only) 🚀

AI-менеджер для сети парков «Джунгли Сити».  
Пилот: Нижний Новгород (`park_slug=nn`).  
MVP-0: бот отвечает по **Facts** (контакты/адрес/график/как добраться) + даёт 1 ссылку на нужную страницу, без RAG.

---

## 1) Требования
- Docker + Docker Compose
- Python 3.11+ (локально, если запускаешь uvicorn не в контейнере)

---

## 2) Быстрый старт

### 2.1 Поднять Postgres
```bash
docker compose up -d postgres
```

Если Docker недоступен, можно поднять Postgres локально через Homebrew (macOS):

```bash
brew install postgresql@16
brew services start postgresql@16
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
```

Создать/обновить пользователя `postgres` с паролем `postgres`:

```bash
psql -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='postgres';"
# если роли нет:
psql -d postgres -c "CREATE ROLE postgres WITH LOGIN SUPERUSER PASSWORD 'postgres';"
# если роль есть:
psql -d postgres -c "ALTER ROLE postgres WITH LOGIN SUPERUSER PASSWORD 'postgres';"
```

### 2.1.1 Поднять Qdrant (для RAG)
```bash
docker compose up -d qdrant
```

Quick-check:

```bash
curl -s http://localhost:6333/ | head
```

Индексирование фикстур (для локальной проверки RAG):

```bash
export RAG_ENABLED=true
python scripts/reindex_kb_fixtures.py
```

### 2.2 Применить схему и seed (вариант через psql)

> Если ты запускаешь Postgres через docker-compose, обычно удобно выполнить команды внутри контейнера.

```bash
docker compose exec postgres psql -U postgres -d postgres -f /sql/schema.sql
docker compose exec postgres psql -U postgres -d postgres -f /sql/seed_nn.sql
```

> Предполагается, что `schema.sql` и `seed_nn.sql` монтируются в контейнер в папку `/sql`.
> См. `docker-compose.yml`.
>
> Если менялась схема, проще всего пересоздать volume: `docker compose down -v` и снова `up`.

Вариант без Docker (локальный Postgres):

```bash
export PGPASSWORD=postgres
psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 -f sql/schema.sql
psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 -f sql/seed_nn.sql
```

### 2.3 Запустить API

Вариант A (локально):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
uvicorn app.main:app --reload --port 8000
```

---

## 3) Проверка работы

### 3.1 Healthcheck

```bash
curl http://localhost:8000/v1/health
```

Ожидаемо:

```json
{"status":"ok"}
```

### 3.2 Тестовый чат (контакты)

```bash
curl -X POST http://localhost:8000/v1/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "park_slug": "nn",
    "channel": "test",
    "session_id": "00000000-0000-0000-0000-000000000001",
    "user_id": "u_demo",
    "message": "Как до вас добраться?"
  }'
```

Ожидаемо:
- в ответе есть адрес/как добраться (из Facts)
- есть 1 ссылка на страницу контактов

---

## 4) QA (минимальный прогон)

Рекомендуемый набор:
- C01–C15 (контакты/как добраться/график)
- X01–X05 (правила/оффер/оператор — пока без интеграций, но ссылки должны быть)

Запуск (при запущенных `postgres` и `uvicorn`):

```bash
python scripts/run_qa.py
```

Baseline по логам (fallback_rate + топ-10 вопросов):

```bash
python scripts/baseline_from_db.py
```

---

## 5) Переменные окружения

- `DATABASE_URL` — строка подключения к Postgres
- `QDRANT_URL` — URL Qdrant (например, `http://localhost:6333`)
- `RAG_ENABLED` — `true|false` (если `false`, бот работает без RAG)
- `EMBEDDINGS_PROVIDER` — `local_hash` (по умолчанию)
- `ADMIN_API_KEY` — ключ для Admin API (заголовок `X-Admin-Key`)

---

## 6) Sanity-check (event_log)

После 1–2 запросов в чат:

```sql
SELECT event_name, count(*) FROM event_log GROUP BY event_name;
```

## 7) DOW (день недели)

В `park_opening_hours` используется `dow: 0=Mon … 6=Sun`.

---

## 8) MVP-1 Sanity-check (leads)

Важно: `session_id` в API/БД — это UUID.

Upsert (один lead на один `session_id`):

```sql
SELECT COUNT(*)
FROM leads l
JOIN parks p ON p.id=l.park_id
WHERE p.slug = 'nn'
  AND l.session_id = '00000000-0000-0000-0000-000000000000'::uuid;
```

`missing_required_slots`/слоты:

```sql
SELECT missing_required_slots, kids_count, kids_age_main, event_date, client_phone
FROM leads l JOIN parks p ON p.id=l.park_id
WHERE p.slug = 'nn'
  AND l.session_id = '00000000-0000-0000-0000-000000000000'::uuid;
```

Лайфхак: взять последний `session_id` из логов:

```sql
SELECT session_id, trace_id, event_name, ts_utc
FROM event_log
ORDER BY ts_utc DESC
LIMIT 20;
```

---

## 9) Admin API (MVP-3)

Все эндпоинты ` /v1/admin/* ` защищены заголовком `X-Admin-Key` (значение = `ADMIN_API_KEY`).

Health:

```bash
curl -H "X-Admin-Key: $ADMIN_API_KEY" http://localhost:8000/v1/admin/health
```

Publish / rollback Facts:

```bash
curl -X POST -H "X-Admin-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  http://localhost:8000/v1/admin/parks/nn/publish -d '{"notes":"manual"}'

curl -X POST -H "X-Admin-Key: $ADMIN_API_KEY" \
  http://localhost:8000/v1/admin/parks/nn/rollback
```

Replace contacts:

```bash
curl -X PUT -H "X-Admin-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  http://localhost:8000/v1/admin/parks/nn/contacts \
  -d '{"items":[{"type":"phone","value":"+7 (999) 000-00-00","is_primary":true}],"reason":"manual"}'
```

KB sources (list/create/patch):

```bash
curl -H "X-Admin-Key: $ADMIN_API_KEY" http://localhost:8000/v1/admin/parks/nn/kb/sources

curl -X POST -H "X-Admin-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  http://localhost:8000/v1/admin/parks/nn/kb/sources \
  -d '{"source_type":"url","source_url":"https://nn.jucity.ru/rules/","title":"Правила","enabled":true}'
```

Smoke publish/rollback:

```bash
python scripts/smoke_publish_rollback.py
```

Smoke admin (MVP-3 publish/rollback flow):

```bash
python tests/run_admin_smoke.py
```
