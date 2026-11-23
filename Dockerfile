FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[ui]"

COPY ui ./ui
COPY data ./data
COPY scripts ./scripts

RUN useradd --create-home app
USER app

EXPOSE 8000 8501
CMD ["uvicorn", "hpm.api:app", "--host", "0.0.0.0", "--port", "8000"]
