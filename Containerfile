FROM docker.io/library/python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY deploy/entrypoint.sh /app/deploy/entrypoint.sh
RUN chmod 755 /app/deploy/entrypoint.sh \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin archimaid

USER 10001
EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
