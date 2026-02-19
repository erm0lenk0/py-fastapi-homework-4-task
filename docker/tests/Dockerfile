FROM python:3.10-slim

# Setting environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=off
ENV ALEMBIC_CONFIG=/usr/src/config/alembic.ini

# Installing dependencies
RUN apt update && apt install -y \
    gcc \
    libpq-dev \
    netcat-openbsd \
    postgresql-client \
    dos2unix \
    && apt clean

# Install Poetry
RUN python -m pip install --upgrade pip && \
    pip install poetry

# Copy dependency files
COPY ./poetry.lock /usr/src/poetry/poetry.lock
COPY ./pyproject.toml /usr/src/poetry/pyproject.toml

# Copy pytest config file
COPY ./pytest.ini /usr/src/config/pytest.ini

# Configure Poetry to avoid creating a virtual environment
RUN poetry config virtualenvs.create false

# Selecting a working directory
WORKDIR /usr/src/poetry

# Install dependencies with Poetry
RUN poetry lock
RUN poetry install --no-root

# Selecting a working directory
WORKDIR /usr/src/fastapi

# Copy the source code
COPY ./src .

COPY ./alembic.ini /usr/src/config/alembic.ini

COPY ./commands /commands
RUN dos2unix /commands/*.sh && chmod +x /commands/*.sh

CMD ["pytest", "-c", "/usr/src/config/pytest.ini", "-m", "e2e", "--maxfail=5", "--disable-warnings", "-v", "--tb=short"]

