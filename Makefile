# POSIX shells. On Windows use the commands in README §2 directly, or swap
# .venv/bin/ for .venv/Scripts/ below.
.PHONY: up down logs seed test api web install reset

up:            ## one command: api + db + minio + web
	docker compose up --build

down:
	docker compose down

reset:         ## drop volumes too (deletes all stored images and cases)
	docker compose down -v

logs:
	docker compose logs -f api

seed:
	docker compose exec api python -m app.seed

test:
	cd api && .venv/bin/python -m pytest -q || python -m pytest -q

install:
	cd api && python -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd web && npm install

api:           ## run the API alone on SQLite + local filesystem storage
	cd api && python -m app.seed && python -m uvicorn app.main:app --reload --port 8000

web:
	cd web && npm run dev
