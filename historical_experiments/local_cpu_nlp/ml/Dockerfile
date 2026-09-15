FROM ghcr.io/astral-sh/uv:0.12.9@sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff AS uv
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
COPY --from=uv /uv /uvx /usr/local/bin/
WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY model-lock.json download_models.py ./
COPY tests ./tests
RUN useradd --uid 10002 --create-home mluser \
    && mkdir -p /models /reports \
    && chown mluser:mluser /models /reports
USER mluser
ENV PATH="/app/.venv/bin:$PATH" HF_HOME=/tmp/huggingface HF_HUB_DISABLE_TELEMETRY=1
ENV OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 TOKENIZERS_PARALLELISM=false
CMD ["pytest", "-q", "-s", "-o", "cache_dir=/tmp/pytest-cache"]
