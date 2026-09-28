# Stage 1: build the Vite SPA. Node is discarded after this stage (PLAN.md Phase 0).
FROM node:20-slim AS web
WORKDIR /web
# package-lock.json is committed and `npm ci` installs it exactly, so the image
# is reproducible (PLAN.md section 5: pin every dependency).
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# Stage 2: runtime. FastAPI + the built SPA as static files. No Node present.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY api/app ./app
COPY api/tests ./tests
COPY api/pytest.ini ./pytest.ini
COPY fixtures ./fixtures
# The official DOGFOOD fixtures stay at the repo root, where run.py looks.
COPY fixtures.json ./fixtures/dogfood.json
# Both acceptance checkers, so they can also be run from inside the container
# with no network at all (docker-compose.offline-proof.yml, README).
COPY run.py check_t3_t4.py .dogfood.toml fixtures.json ./checks/
COPY --from=web /web/dist ./static

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
