FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/scripts \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_PREFERENCE=only-system \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/dados /app/.venv \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser pyproject.toml uv.lock ./

USER appuser
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=appuser:appuser scripts/ ./scripts/
COPY --chown=appuser:appuser app.py ./

EXPOSE 8501

ENTRYPOINT ["uv", "run", "--frozen", "--no-dev", "--no-sync", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
