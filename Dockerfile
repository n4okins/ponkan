FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/tsconfig.json web/index.html ./
COPY web/src ./src
RUN npm install --no-audit --no-fund && npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PONKAN_WEB_DIR=/app/web-dist
WORKDIR /app
RUN useradd --create-home --uid 10001 ponkan
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts/entrypoint.sh /entrypoint.sh
COPY --from=web /web/dist /app/web-dist
USER ponkan
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
