FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*
# Copy configuration first for layer caching
COPY pyproject.toml /app/
RUN pip install --no-cache-dir -e ".[dev]"
COPY . /app/
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]