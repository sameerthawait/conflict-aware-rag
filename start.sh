#!/bin/bash
set -e

# Change ownership of mounted database, log, and cache directories to appuser
chown -R appuser:appgroup /app/data/chroma_db /app/logs /home/appuser/.cache

echo "Checking SentenceTransformer model..."

su -s /bin/bash appuser -c "python - <<EOF
try:
    import torch.utils._pytree as pytree
    if not hasattr(pytree, 'register_pytree_node'):
        def register_pytree_node(type_to_register, flatten_fn, unflatten_fn, *args, **kwargs):
            return pytree._register_pytree_node(type_to_register, flatten_fn, unflatten_fn)
        pytree.register_pytree_node = register_pytree_node
except ImportError:
    pass

from sentence_transformers import SentenceTransformer
SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
print('Model ready.')
EOF"

echo "Starting API..."

exec su -s /bin/bash appuser -c "exec uvicorn src.api.main:app \
    --host 0.0.0.0 \
    --port 8000"