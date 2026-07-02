# Dockerfile
#
# Single-container development image for MarketMind.
#
# Design decisions (Phase 1):
#   - One Dockerfile, not multi-stage production build.
#     Production hardening is deferred until the research pipeline
#     is proven and worth deploying.
#   - Installs only foundation dependencies. ML/data deps added when needed.
#   - Non-root user for security hygiene even in development.
#   - Layer order maximises cache reuse: dependencies before source code.
#
# Build:
#   docker build -t marketmind:dev .
#
# Run (interactive shell):
#   docker run --rm -it -v $(pwd):/app -e MM_ENVIRONMENT=local marketmind:dev bash
#
# Run tests:
#   docker run --rm -v $(pwd):/app -e MM_ENVIRONMENT=test marketmind:dev \
#     pytest tests/ -m "not slow"

FROM python:3.11-slim

# Metadata
LABEL maintainer="MarketMind Contributors"
LABEL description="MarketMind Quantitative Research Platform — Development Image"
LABEL version="0.1.0"

# System dependencies
# build-essential: needed by some Python packages that compile C extensions
# curl: useful for health checks and debugging
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
# Running as root in a container is poor practice even for development.
RUN groupadd --gid 1001 marketmind \
    && useradd --uid 1001 --gid marketmind --shell /bin/bash --create-home marketmind

# Set working directory
WORKDIR /app

# Upgrade pip before installing dependencies
RUN pip install --no-cache-dir --upgrade pip

# Copy only dependency files first (maximises layer cache)
# If only source code changes, this layer is not rebuilt.
COPY pyproject.toml ./

# Install the package in editable mode with dev dependencies.
# The source code isn't copied yet — we mount it as a volume during development.
# When building for CI without a volume mount, the COPY below provides it.
RUN pip install --no-cache-dir -e ".[dev]"

# Copy the rest of the source (used in CI where volumes aren't mounted)
COPY --chown=marketmind:marketmind . .

# Switch to non-root user
USER marketmind

# Environment defaults (overridable at runtime)
ENV MM_ENVIRONMENT=local
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default command: show platform info
CMD ["marketmind", "info"]
