FROM python:3.12-slim

# Install uv (static binary, no separate Python install needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cached layer) using the lockfile for reproducible installs
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Now copy the rest of the app
COPY . .

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
