FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    # Where Hugging Face keeps downloaded models (the sentiment model is baked in below).
    HF_HOME=/app/hf-cache
WORKDIR /app

# The app runs as a normal user, who owns data/ and the model cache (Hugging Face writes small lock files there).
# Created first so the model is downloaded straight as this user: a `chown -R` afterwards would copy the
# whole 1 GB model into a second image layer.
RUN useradd --create-home --uid 1000 memory && mkdir -p /app/data /app/hf-cache && chown memory /app/data /app/hf-cache

# --- Sentiment model (app/sentiment/) ---
# These layers come before the app code, so changing the code doesn't re-download ~1.5 GB.
# WITH_SENTIMENT=false leaves the model out (a ~500 MB image that fits a 1 GB server); then set
# SENTIMENT_ENABLED=false too, as docker-compose.free.yml does.
ARG WITH_SENTIMENT=true
# CPU-only PyTorch: the default wheel adds ~2 GB of GPU (CUDA) libraries a CPU server never uses.
RUN if [ "$WITH_SENTIMENT" = "true" ]; then \
        pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install "transformers>=4.44"; \
    fi
# Download the model at build time, so containers start ready and never need Hugging Face at runtime.
# Change it with:  docker compose build --build-arg SENTIMENT_MODEL=...  (and set SENTIMENT_MODEL in .env to match)
ARG SENTIMENT_MODEL=vishnuexe/TamilSense-model
USER memory
RUN if [ "$WITH_SENTIMENT" = "true" ]; then \
        python -c "from transformers import pipeline; pipeline('text-classification', model='${SENTIMENT_MODEL}')"; \
    fi
USER root

# --- The app ---
# Dependencies before the code, so a code change doesn't reinstall them. torch and transformers
# (for sentiment) are already installed above when WITH_SENTIMENT=true.
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-deps .

COPY alembic.ini ./
COPY alembic ./alembic

USER memory
EXPOSE 8000
# Migrations run on start; the worker service overrides the command.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
