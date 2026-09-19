FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY config ./config
RUN mkdir -p data logs
ENV PYTHONUNBUFFERED=1
CMD ["wq-evoforge", "run"]
