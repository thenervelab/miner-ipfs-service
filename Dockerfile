# Use an official Python runtime as the base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for Poetry and Python
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Add Poetry to PATH
ENV PATH="/root/.local/bin:${PATH}"

# Copy only the dependency files first (for better layer caching)
COPY pyproject.toml poetry.lock* README.md ./

# Install dependencies with Poetry (without the project)
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi --no-root

# Copy the rest of the application code
COPY . .

# Install the project itself
RUN poetry install --only main --no-interaction --no-ansi

# Run the application
CMD ["poetry", "run", "python", "-m", "hippius.miner_service"]