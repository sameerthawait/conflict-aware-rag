try:
    import torch.utils._pytree as pytree
    if not hasattr(pytree, 'register_pytree_node'):
        def register_pytree_node(type_to_register, flatten_fn, unflatten_fn, *args, **kwargs):
            return pytree._register_pytree_node(type_to_register, flatten_fn, unflatten_fn)
        pytree.register_pytree_node = register_pytree_node
except ImportError:
    pass

import time
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
sentences = ["This is a test sentence."] * 100
start = time.time()
_ = model.encode(sentences, batch_size=32, show_progress_bar=False)
print('Embedding 100 sentences took', time.time() - start, 'seconds')
