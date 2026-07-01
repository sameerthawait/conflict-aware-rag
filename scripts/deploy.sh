#!/usr/bin/env bash

# Set bash options for robust error handling
set -eo pipefail

# Ensure working directory is the project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

echo "=================================================="
echo "🚀 Starting Preflight Deployment Verification"
echo "=================================================="

# 1. Run evaluation tests and block deployment on failures
echo "🧪 Running RAG Evaluation Pipeline..."
if ! python scripts/run_evaluation.py --log-level WARNING; then
    echo "❌ DEPLOYMENT ABORTED: RAG Evaluation metrics dropped below production thresholds."
    exit 1
fi

echo "✔ RAG Evaluation thresholds successfully passed!"
echo "--------------------------------------------------"

# 2. Run unit tests
echo "🧪 Running PyTest Suite..."
if ! python -m pytest tests/; then
    echo "❌ DEPLOYMENT ABORTED: Unit tests failed."
    exit 1
fi

echo "✔ Unit tests successfully passed!"
echo "--------------------------------------------------"

# 3. Check for deploy targets
DEPLOY_TARGET="${1:-dry-run}"

if [ "${DEPLOY_TARGET}" = "docker" ]; then
    echo "📦 Building Docker image..."
    IMAGE_NAME="rag-system-api:latest"
    
    if ! docker build -t "${IMAGE_NAME}" .; then
        echo "❌ DEPLOYMENT ABORTED: Docker build failed."
        exit 1
    fi
    
    echo "✔ Docker image '${IMAGE_NAME}' successfully built!"
    echo "🚀 Run 'docker compose up -d' to start the system."
    
elif [ "${DEPLOY_TARGET}" = "dry-run" ]; then
    echo "✨ Dry-run complete. Preflight verification was successful!"
    echo "💡 Run './scripts/deploy.sh docker' to build the docker container."
else
    echo "⚠️ Unknown target '${DEPLOY_TARGET}'. Skipping container build."
    echo "✨ Preflight verification was successful!"
fi

echo "=================================================="
echo "✔ Verification Complete. System is deployable!"
echo "=================================================="
exit 0
