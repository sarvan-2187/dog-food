# Stage 1: build the Vite SPA. Node is discarded after this stage (PLAN.md Phase 0).
FROM node:20-slim AS web
WORKDIR /web
# package-lock.json is committed and `npm ci` installs it exactly, so the image
# is reproducible (PLAN.md section 5: pin every dependency).
COPY src/web/package.json src/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY src/web/ ./
RUN npm run build

# Stage 2: runtime. FastAPI + the built SPA as static files. No Node present.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY src/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/api/app ./app
COPY tests/api ./tests
COPY src/api/pytest.ini ./pytest.ini
COPY fixtures ./fixtures
# The official DOGFOOD fixtures stay at the repo root, where run.py looks.
COPY fixtures.json ./fixtures/dogfood.json
COPY --from=web /web/dist ./static

EXPOSE 8000
# app/serve.py runs uvicorn with its transport-level DoS limits (concurrency,
# keep-alive, backlog, 16 KB request head) and a 10 s header timeout against
# slow-loris; app/protection.py covers the application level.
CMD ["python", "-m", "app.serve"]
