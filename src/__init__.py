# Central PyTorch / Transformers compatibility patch
try:
    import torch.utils._pytree as pytree
    if not hasattr(pytree, 'register_pytree_node'):
        def register_pytree_node(type_to_register, flatten_fn, unflatten_fn, *args, **kwargs):
            return pytree._register_pytree_node(type_to_register, flatten_fn, unflatten_fn)
        pytree.register_pytree_node = register_pytree_node
except ImportError:
    pass
