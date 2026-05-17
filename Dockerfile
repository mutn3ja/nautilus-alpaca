FROM python:3.14-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml README.md ./
COPY nautilus_alpaca/ nautilus_alpaca/
COPY examples/ examples/

RUN uv pip install --system -e .
