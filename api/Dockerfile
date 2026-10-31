FROM python:3.12-slim

WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY copiloto ./copiloto
COPY api ./api
COPY data ./data

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# COPILOTO_API_TOKEN deve ser definido no ambiente (ver docker-compose.yml).
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
