#!/usr/bin/env bash

# Set bash options for safety
set -euo pipefail

# Configurations
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS=7
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="rag_backup_${TIMESTAMP}.tar.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

# Paths to back up
CHROMA_DIR="data/chroma"
BM25_INDEX="data/bm25_index.pkl"
CONFIG_DIR="config"
PROMPTS_DIR="prompts"
DATASETS_DIR="data/golden_dataset"

# Cloud Storage Configuration (optional target e.g. s3://my-rag-backups)
BUCKET_URI="${BACKUP_BUCKET_URI:-}"

echo "=================================================="
echo "💾 Starting RAG System Data Backup"
echo "Timestamp: $(date)"
echo "=================================================="

# Ensure backup folder exists
mkdir -p "${BACKUP_DIR}"

# Build archive file list dynamically based on existence
ARCHIVE_FILES=()

if [ -d "${CHROMA_DIR}" ]; then
    ARCHIVE_FILES+=("${CHROMA_DIR}")
else
    echo "⚠️  Chroma storage directory not found at ${CHROMA_DIR}. Skipping."
fi

if [ -f "${BM25_INDEX}" ]; then
    ARCHIVE_FILES+=("${BM25_INDEX}")
else
    echo "⚠️  BM25 Index not found at ${BM25_INDEX}. Skipping."
fi

if [ -d "${CONFIG_DIR}" ]; then
    ARCHIVE_FILES+=("${CONFIG_DIR}")
fi

if [ -d "${PROMPTS_DIR}" ]; then
    ARCHIVE_FILES+=("${PROMPTS_DIR}")
fi

if [ -d "${DATASETS_DIR}" ]; then
    ARCHIVE_FILES+=("${DATASETS_DIR}")
fi

if [ ${#ARCHIVE_FILES[@]} -eq 0 ]; then
    echo "❌ ERROR: No target data files found to back up. Aborting."
    exit 1
fi

# Create tar.gz archive
echo "📦 Archiving files into ${BACKUP_PATH}..."
tar -czf "${BACKUP_PATH}" "${ARCHIVE_FILES[@]}"
echo "✔ Archive created successfully (Size: $(du -sh "${BACKUP_PATH}" | cut -f1))"

# Upload to S3/GCS if bucket is configured
if [ -n "${BUCKET_URI}" ]; then
    echo "☁ Uploading archive to cloud storage: ${BUCKET_URI}..."
    if [[ "${BUCKET_URI}" =~ ^s3:// ]]; then
        if command -v aws &> /dev/null; then
            aws s3 cp "${BACKUP_PATH}" "${BUCKET_URI}/${BACKUP_NAME}"
            echo "✔ Uploaded to AWS S3!"
        else
            echo "❌ ERROR: aws-cli is not installed. Cloud upload failed."
        fi
    elif [[ "${BUCKET_URI}" =~ ^gs:// ]]; then
        if command -v gcloud &> /dev/null; then
            gcloud storage cp "${BACKUP_PATH}" "${BUCKET_URI}/${BACKUP_NAME}"
            echo "✔ Uploaded to Google Cloud Storage!"
        else
            echo "❌ ERROR: gcloud is not installed. Cloud upload failed."
        fi
    else
        echo "⚠️  Unknown cloud storage protocol in URI: ${BUCKET_URI}. Skipping cloud upload."
    fi
fi

# Enforce local retention limit
echo "🧹 Cleaning up local backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "rag_backup_*.tar.gz" -type f -mtime +"${RETENTION_DAYS}" -exec rm -f {} \;
echo "✔ Cleanup complete."

echo "=================================================="
echo "✔ Backup Successful: ${BACKUP_NAME}"
echo "=================================================="
exit 0
