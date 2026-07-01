import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

# Initialize structured logger
logger = logging.getLogger("rag_system.api.query_queue")


@dataclass(order=True)
class QueueItem:
    """Represents a query request item queued for execution."""
    priority: int  # Lower value = higher priority (e.g. 1 for premium, 2 for standard)
    timestamp: float  # FIFO sorting for items with matching priority
    req_id: str = field(compare=False)
    task_fn: Callable = field(compare=False)
    future: asyncio.Future = field(compare=False)


class QueryQueue:
    """A priority-based asynchronous query queue enforcing request concurrency limits and depth gates."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initializes the QueryQueue.

        Args:
            config: System configuration dictionary.
        """
        self.config = config
        
        con_conf = config.get("concurrency", {})
        self.concurrency_limit: int = con_conf.get("max_concurrent_queries", 20)
        self.depth_limit: int = con_conf.get("queue_depth_limit", 50)

        # Priority queue matching depth limit
        self._queue: asyncio.PriorityQueue[QueueItem] = asyncio.PriorityQueue(maxsize=self.depth_limit)
        
        # Background worker task references
        self._workers: List[asyncio.Task] = []
        self._running = False

    def start_workers(self) -> None:
        """Starts background worker tasks matching the concurrency limit."""
        if self._running:
            return
        
        self._running = True
        logger.info(f"Starting {self.concurrency_limit} async background workers for RAG query queue...")
        for i in range(self.concurrency_limit):
            task = asyncio.create_task(self._worker_loop(i))
            self._workers.append(task)

    async def stop_workers(self) -> None:
        """Gracefully terminates background worker tasks."""
        self._running = False
        logger.info("Stopping background query queue workers...")
        for task in self._workers:
            task.cancel()
        
        # Wait for all workers to shut down
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()

    async def _worker_loop(self, worker_id: int) -> None:
        """Background consumer worker loop."""
        while self._running:
            try:
                # Retrieve next highest priority item
                item = await self._queue.get()
                logger.debug(f"Worker {worker_id} acquired item: ID={item.req_id} (Priority={item.priority})")

                try:
                    # Run RAG query task
                    # Wrap blocking task_fn in threadpool if it is synchronous,
                    # but if it is coroutine, we can await it directly.
                    if asyncio.iscoroutinefunction(item.task_fn):
                        result = await item.task_fn()
                    else:
                        # Fallback for sync functions
                        result = await asyncio.to_thread(item.task_fn)
                    
                    if not item.future.cancelled():
                        item.future.set_result(result)
                except Exception as e:
                    logger.error(f"Worker {worker_id} encountered exception for request {item.req_id}: {str(e)}")
                    if not item.future.cancelled():
                        item.future.set_exception(e)
                finally:
                    self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue worker {worker_id} crashed: {str(e)}. Restarting...")
                await asyncio.sleep(0.5)

    async def submit(self, req_id: str, tier: str, task_fn: Callable) -> Any:
        """Enqueues a query request and returns the result once processed.

        Args:
            req_id: Request tracking ID.
            tier: User tier ('premium' or 'standard').
            task_fn: The callable query task function.

        Returns:
            The output of the task function.

        Raises:
            asyncio.QueueFull: If queue depth limit is exceeded.
        """
        # 1. Enforce Queue Depth Check
        current_size = self._queue.qsize()
        if current_size >= self.depth_limit:
            logger.warning(f"[{req_id}] Request rejected: Queue is full (depth={current_size}/{self.depth_limit}).")
            raise asyncio.QueueFull("Queue limit exceeded. Server is busy.")

        # 2. Determine Priority (lower integer = higher priority)
        # Premium: 1, Standard: 2
        priority = 1 if tier.lower() == "premium" else 2

        # 3. Queue item and await completion future
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        item = QueueItem(
            priority=priority,
            timestamp=time.time(),
            req_id=req_id,
            task_fn=task_fn,
            future=future
        )

        # Enqueue item
        await self._queue.put(item)
        logger.info(f"[{req_id}] Enqueued request tier '{tier}' (Queue depth: {self._queue.qsize()}/{self.depth_limit}).")

        # Block caller until worker finishes the task
        return await future

    def get_depth(self) -> int:
        """Returns the current number of requests waiting in the queue."""
        return self._queue.qsize()
