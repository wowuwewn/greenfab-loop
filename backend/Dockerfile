FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/huggingface/sentence-transformers

WORKDIR /app

ARG INSTALL_MATCH_RUNTIME=false
ARG INSTALL_STORAGE_RUNTIME=false

RUN addgroup --system greenfab && adduser --system --ingroup greenfab greenfab

COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

RUN if [ "$INSTALL_MATCH_RUNTIME" = "true" ]; then \
        bash scripts/install_match_runtime.sh; \
    elif [ "$INSTALL_STORAGE_RUNTIME" = "true" ]; then \
        pip install --no-cache-dir '.[storage]'; \
    else \
        pip install --no-cache-dir .; \
    fi \
    && mkdir -p /app/var/evidence /app/.data/chroma /app/.cache/huggingface/sentence-transformers \
    && chown -R greenfab:greenfab /app

USER greenfab

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
