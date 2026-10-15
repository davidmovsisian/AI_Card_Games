FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home appuser \
    && chown appuser:appuser /app

COPY --chown=appuser:appuser ai_player.py engine.py main.py models.py graph.py ./
COPY --chown=appuser:appuser frontend ./frontend
COPY --chown=appuser:appuser prompts ./prompts

USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
