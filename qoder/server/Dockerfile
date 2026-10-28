FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY server/pyproject.toml ./
COPY server/nullpath ./nullpath
RUN pip install --no-cache-dir .
COPY db /db
EXPOSE 8080
CMD ["uvicorn", "nullpath.api:app", "--host", "0.0.0.0", "--port", "8080"]
