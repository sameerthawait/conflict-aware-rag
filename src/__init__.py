# Central PyTorch / Transformers compatibility patch
try:
    import torch.utils._pytree as pytree
    if not hasattr(pytree, 'register_pytree_node'):
        from typing import Callable, Any, cast
        def register_pytree_node(type_to_register, flatten_fn, unflatten_fn, *args, **kwargs):
            return pytree._register_pytree_node(type_to_register, flatten_fn, unflatten_fn)
        # Cast to expected signature for MyPy
        pytree.register_pytree_node = cast(Callable[[type, Callable[[Any], tuple[list[Any], Any]], Callable[[Any, Any], Any]], Any], register_pytree_node)  # type: ignore[assignment]
except ImportError:
    pass
