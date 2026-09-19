FROM python:3.14-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.17
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY services/api/app ./services/api/app
RUN useradd --create-home api
USER api
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "services/api", "--host", "0.0.0.0", "--port", "8000"]
