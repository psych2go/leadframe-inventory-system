FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/uploads /app/data /app/logs \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser . .

EXPOSE 8000

USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
