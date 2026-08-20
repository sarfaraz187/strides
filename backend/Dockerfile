FROM python:3.11-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.11-slim AS runtime

RUN useradd --create-home appuser
WORKDIR /app

COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

EXPOSE 8080
CMD ["sh", "-c", "uvicorn backend.agent:app --host 0.0.0.0 --port ${PORT:-8080}"]
