# ==========================================
# STAGE 1 - BUILDER AND RUNTIME (Unified for GPU/CUDA compatibility)
# ==========================================
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

LABEL maintainer="Sameer Thawait"
LABEL version="1.0.0"
LABEL description="Conflict-Aware RAG API with GPU Acceleration"

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    python3 \
    python3-dev \
    python3-pip \
    python3-distutils \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*
RUN ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Create non-root application user
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /bin/bash appuser

# Copy requirements
COPY requirements.txt .

# Install PyTorch with CUDA 11.8 support, then other packages
RUN pip install --no-cache-dir torch==2.1.0+cu118 --index-url https://download.pytorch.org/whl/cu118 && \
    pip install --no-cache-dir -r requirements.txt

ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HF_HUB_DISABLE_SYMLINKS_WARNING=1

# Copy project source directories
COPY --chown=appuser:appgroup src/ /app/src/
COPY --chown=appuser:appgroup config/ /app/config/
COPY --chown=appuser:appgroup prompts/ /app/prompts/
COPY --chown=appuser:appgroup scripts/ /app/scripts/
COPY --chown=appuser:appgroup start.sh /app/start.sh

# Set ownership of data and logs directories and make entrypoint executable
RUN mkdir -p /app/logs /app/data/chroma && \
    chown -R appuser:appgroup /app && \
    chmod +x /app/start.sh

EXPOSE 8000

# Docker Healthcheck instruction
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health/ready || exit 1

ENTRYPOINT ["/app/start.sh"]
