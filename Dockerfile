FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install uv && uv pip install --system .

COPY src/ ./src/

ENV MCP_TRANSPORT=http
ENV PORT=8000

EXPOSE 8000

CMD ["python", "src/server.py"]
