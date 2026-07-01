import os
import time
import logging
from typing import Dict, Any, Optional, Tuple
from fastapi import APIRouter, Depends, status, HTTPException, Header
import redis

# Define audit logging stream
audit_logger = logging.getLogger("rag_system.audit.cost")
logger = logging.getLogger("rag_system.monitoring.cost_tracker")

router = APIRouter(prefix="/admin", tags=["Cost Control & Administration"])
cost_tracker_instance: Optional["CostTracker"] = None


class BudgetExceededError(Exception):
    """Raised when daily or monthly token budgets are fully exhausted."""
    pass


class CostTracker:
    """Tracks token consumption, estimates costs, and enforces budget caps per API key."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initializes the CostTracker.

        Args:
            config: System configuration dictionary.
        """
        self.config = config
        
        costs_conf = config.get("costs", {})
        self.pricing: Dict[str, float] = costs_conf.get("pricing", {
            "prompt_tokens_per_million": 3.0,
            "completion_tokens_per_million": 15.0
        })

        self.budgets: Dict[str, int] = costs_conf.get("budgets", {
            "daily_token_budget": 500000,
            "monthly_token_budget": 10000000
        })

        redis_conf = config.get("redis", {})
        self.redis_enabled: bool = redis_conf.get("enabled", True)
        self.redis_url: str = redis_conf.get("url", os.getenv("REDIS_URL", "redis://localhost:6379/0"))

        self.redis_client: Optional[redis.Redis] = None
        if self.redis_enabled:
            try:
                self.redis_client = redis.Redis.from_url(
                    self.redis_url,
                    socket_timeout=1.0,
                    socket_connect_timeout=1.0,
                    decode_responses=True
                )
                self.redis_client.ping()
                logger.info("Cost tracker successfully connected to Redis.")
            except Exception as e:
                logger.warning(f"Cost tracker failed to connect to Redis: {str(e)}. Using memory fallback.")
                self.redis_client = None

        # In-memory backup structures
        # format: {key_hash: (day_date_str, daily_token_count, monthly_token_count)}
        self._in_memory_budgets: Dict[str, Dict[str, Any]] = {}

    def _get_dates(self) -> Tuple[str, str]:
        """Returns the current day (YYYY-MM-DD) and current month (YYYY-MM) strings."""
        now = time.gmtime()
        return time.strftime("%Y-%m-%d", now), time.strftime("%Y-%m", now)

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimates request cost in USD based on pricing configurations."""
        p_price = self.pricing.get("prompt_tokens_per_million", 3.0) / 1000000.0
        c_price = self.pricing.get("completion_tokens_per_million", 15.0) / 1000000.0
        return (prompt_tokens * p_price) + (completion_tokens * c_price)

    def verify_budget(self, key_hash: str, key_name: str) -> None:
        """Asserts that the API key does not exceed token budgets before execution.

        Args:
            key_hash: Hashed API key.
            key_name: Key name.

        Raises:
            BudgetExceededError: If daily/monthly budgets are exhausted.
        """
        day_str, month_str = self._get_dates()
        daily_limit = self.budgets.get("daily_token_budget", 500000)
        monthly_limit = self.budgets.get("monthly_token_budget", 10000000)

        # 1. Try verifying via Redis
        if self.redis_client:
            try:
                d_key = f"cost:{key_hash}:{day_str}"
                m_key = f"cost:{key_hash}:{month_str}"
                
                daily_used = int(self.redis_client.get(d_key) or 0)
                monthly_used = int(self.redis_client.get(m_key) or 0)

                # Hard budget enforcement
                if daily_used >= daily_limit:
                    raise BudgetExceededError(f"Daily token budget exhausted for key '{key_name}'.")
                if monthly_used >= monthly_limit:
                    raise BudgetExceededError(f"Monthly token budget exhausted for key '{key_name}'.")
                return
            except BudgetExceededError:
                raise
            except Exception as e:
                logger.error(f"Redis budget verify failed: {str(e)}. Using memory fallback.")

        # 2. In-memory fallback verification
        entry = self._in_memory_budgets.get(key_hash, {})
        if entry.get("day") == day_str:
            daily_used = entry.get("daily_used", 0)
        else:
            daily_used = 0

        if entry.get("month") == month_str:
            monthly_used = entry.get("monthly_used", 0)
        else:
            monthly_used = 0

        if daily_used >= daily_limit:
            raise BudgetExceededError(f"Daily token budget exhausted for key '{key_name}'.")
        if monthly_used >= monthly_limit:
            raise BudgetExceededError(f"Monthly token budget exhausted for key '{key_name}'.")

    def record_usage(
        self,
        key_hash: str,
        key_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        request_id: str = "N/A",
        client_ip: Optional[str] = None
    ) -> float:
        """Records token consumption post-completion, estimates costs, and audits warning levels.

        Also tracks client IP usage if client_ip is provided.
        """
        tokens_added = prompt_tokens + completion_tokens
        cost_est = self.calculate_cost(prompt_tokens, completion_tokens)
        day_str, month_str = self._get_dates()
        
        daily_limit = self.budgets.get("daily_token_budget", 500000)
        monthly_limit = self.budgets.get("monthly_token_budget", 10000000)

        # Track IP usage
        if client_ip:
            self.track_ip_usage(client_ip, tokens_added)

        daily_used = 0
        monthly_used = 0

        # 1. Update Redis
        if self.redis_client:
            try:
                d_key = f"cost:{key_hash}:{day_str}"
                m_key = f"cost:{key_hash}:{month_str}"
                
                # Transaction increment
                pipe = self.redis_client.pipeline()
                pipe.incrby(d_key, tokens_added)
                pipe.incrby(m_key, tokens_added)
                # Keep daily keys for 2 days, monthly keys for 60 days
                pipe.expire(d_key, 172800)
                pipe.expire(m_key, 5184000)
                
                daily_used, monthly_used, _, _ = pipe.execute()
            except Exception as e:
                logger.error(f"Redis usage recording failed: {str(e)}.")
                daily_used = 0  # Trigger fallback

        # 2. In-memory update (always update as fallback/shadow sync)
        entry = self._in_memory_budgets.setdefault(key_hash, {
            "day": day_str,
            "month": month_str,
            "daily_used": 0,
            "monthly_used": 0
        })

        if entry["day"] == day_str:
            entry["daily_used"] += tokens_added
        else:
            entry["day"] = day_str
            entry["daily_used"] = tokens_added

        if entry["month"] == month_str:
            entry["monthly_used"] += tokens_added
        else:
            entry["month"] = month_str
            entry["monthly_used"] = tokens_added

        if daily_used == 0:
            daily_used = entry["daily_used"]
            monthly_used = entry["monthly_used"]

        # 3. Soft Alert Auditing (80% of budget)
        if daily_used >= daily_limit * 0.8:
            audit_logger.warning(
                f"[{request_id}] Soft Warning: Key '{key_name}' daily token usage ({daily_used}) "
                f"exceeded 80% of budget limit ({daily_limit})."
            )
        if monthly_used >= monthly_limit * 0.8:
            audit_logger.warning(
                f"[{request_id}] Soft Warning: Key '{key_name}' monthly token usage ({monthly_used}) "
                f"exceeded 80% of budget limit ({monthly_limit})."
            )

        logger.info(
            f"[{request_id}] Key '{key_name}' cost: ${cost_est:.6f} | "
            f"Daily used: {daily_used}/{daily_limit} ({daily_used/daily_limit*100:.1f}%)"
        )
        return cost_est

    def check_ip_budget(self, ip_address: str) -> bool:
        """Checks if a client IP address has exceeded its daily token budget (50,000 tokens)."""
        if not self.redis_client:
            return True
        day_str, _ = self._get_dates()
        d_key = f"cost:ip:{ip_address}:{day_str}"
        try:
            daily_used = int(self.redis_client.get(d_key) or 0)
            if daily_used >= 50000:
                audit_logger.warning(
                    f"Security Block: IP {ip_address} has exceeded its daily token budget limit of 50,000. Used: {daily_used}"
                )
                return False
        except Exception as e:
            logger.warning(f"Error checking IP budget in Redis for {ip_address}: {str(e)}")
        return True

    def track_ip_usage(self, ip_address: str, tokens: int) -> None:
        """Increments the daily token usage count for a client IP address."""
        if not self.redis_client or tokens <= 0:
            return
        day_str, _ = self._get_dates()
        d_key = f"cost:ip:{ip_address}:{day_str}"
        try:
            pipe = self.redis_client.pipeline()
            pipe.incrby(d_key, tokens)
            pipe.expire(d_key, 172800)  # Expire after 2 days
            pipe.execute()
        except Exception as e:
            logger.warning(f"Error tracking IP usage in Redis for {ip_address}: {str(e)}")


# Dependency to protect admin routes
async def admin_auth(x_api_key: str = Header(...)) -> Dict[str, Any]:
    """Dependency verifying that caller holds the admin key."""
    from src.api.main import authenticator
    if not authenticator:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is disabled."
        )

    # Validate header key
    # Use standard authenticator verification
    try:
        # Mock request to satisfy dependency signature
        mock_req = type('Request', (object,), {"state": type('State', (object,), {"request_id": "ADMIN"}), "client": None})()
        key_info = await authenticator.authenticate(mock_req, api_key=x_api_key)
        # Ensure it is the admin-key or premium tier
        if key_info["name"] != "admin-key":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin authorization required."
            )
        return key_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}"
        )


@router.get(
    "/costs",
    status_code=status.HTTP_200_OK,
    summary="Admin token consumption and pricing report."
)
def get_costs_report(admin: Dict[str, Any] = Depends(admin_auth)) -> Dict[str, Any]:
    """Returns the aggregated daily and monthly token consumption and estimated costs across all API keys."""
    global cost_tracker_instance
    if not cost_tracker_instance:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cost tracker is not initialized."
        )

    # Gather usage stats from Redis/memory
    stats = {}
    day_str, month_str = cost_tracker_instance._get_dates()
    hashed_keys = cost_tracker_instance.config.get("security", {}).get("hashed_api_keys", {})

    for key_hash, key_info in hashed_keys.items():
        name = key_info["name"]
        daily_used = 0
        monthly_used = 0

        # Query Redis if connected
        if cost_tracker_instance.redis_client:
            try:
                daily_used = int(cost_tracker_instance.redis_client.get(f"cost:{key_hash}:{day_str}") or 0)
                monthly_used = int(cost_tracker_instance.redis_client.get(f"cost:{key_hash}:{month_str}") or 0)
            except Exception:
                pass

        # Memory fallback values
        if daily_used == 0 or monthly_used == 0:
            mem_entry = cost_tracker_instance._in_memory_budgets.get(key_hash, {})
            if mem_entry.get("day") == day_str:
                daily_used = mem_entry.get("daily_used", 0)
            if mem_entry.get("month") == month_str:
                monthly_used = mem_entry.get("monthly_used", 0)

        # Estimate costs (assume 70% prompt / 30% completion splits for estimates)
        est_daily_cost = cost_tracker_instance.calculate_cost(
            int(daily_used * 0.7), int(daily_used * 0.3)
        )
        est_monthly_cost = cost_tracker_instance.calculate_cost(
            int(monthly_used * 0.7), int(monthly_used * 0.3)
        )

        stats[name] = {
            "tier": key_info["tier"],
            "daily_tokens_used": daily_used,
            "daily_token_limit": cost_tracker_instance.budgets["daily_token_budget"],
            "daily_budget_pct": f"{daily_used / cost_tracker_instance.budgets['daily_token_budget'] * 100:.2f}%",
            "estimated_daily_cost_usd": est_daily_cost,
            "monthly_tokens_used": monthly_used,
            "monthly_token_limit": cost_tracker_instance.budgets["monthly_token_budget"],
            "monthly_budget_pct": f"{monthly_used / cost_tracker_instance.budgets['monthly_token_budget'] * 100:.2f}%",
            "estimated_monthly_cost_usd": est_monthly_cost,
        }

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pricing_model": cost_tracker_instance.pricing,
        "api_keys_usage": stats
    }
