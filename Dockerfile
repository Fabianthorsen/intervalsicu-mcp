FROM python:3.12-slim

WORKDIR /app

# Install from uv.lock, not pyproject.toml: the lockfile pins fastmcp exactly,
# so every deploy runs the version the repo was tested against. An unpinned
# resolve here means two clones of this repo can deploy different OAuth code.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
ENV MCP_TRANSPORT=http
ENV PORT=8000

EXPOSE 8000

CMD ["python", "src/server.py"]
