import os
import sys
import logging
import json
from datetime import datetime
from contextvars import ContextVar
from typing import Dict, Any

# Context variable to hold request tracking IDs across async calls
request_id_var: ContextVar[str] = ContextVar("request_id", default="N/A")


class JSONFormatter(logging.Formatter):
    """Custom logging formatter that serializes records into structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        # Build base log payload
        log_payload = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "request_id": request_id_var.get(),
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage()
        }

        # Include latency durations if passed extra
        if hasattr(record, "duration_ms"):
            log_payload["duration_ms"] = getattr(record, "duration_ms")

        # Include stack trace if exception occurred
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload)


class ErrorFilter(logging.Filter):
    """Filters records to only allow levels WARNING and above (errors)."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING


def configure_logging(config: Dict[str, Any]) -> None:
    """Configures the unified JSON structured logging streams and destinations.

    Args:
        config: System configuration dictionary.
    """
    system_conf = config.get("system", {})
    log_level_str = system_conf.get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Ensure logs output directory exists
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # Initialize shared formatter
    json_formatter = JSONFormatter()

    # 1. Root Logger Setup
    root_logger = logging.getLogger()
    # Reset existing handlers to prevent duplicate outputs
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
    root_logger.setLevel(log_level)

    # Console stdout handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(json_formatter)
    root_logger.addHandler(console_handler)

    # 2. Access Stream Log
    access_handler = logging.FileHandler(os.path.join(log_dir, "access.log"), encoding="utf-8")
    access_handler.setFormatter(json_formatter)
    root_logger.addHandler(access_handler)

    # 3. Error Stream Log (Filters level >= WARNING)
    error_handler = logging.FileHandler(os.path.join(log_dir, "error.log"), encoding="utf-8")
    error_handler.setFormatter(json_formatter)
    error_handler.addFilter(ErrorFilter())
    root_logger.addHandler(error_handler)

    # 4. Security Audit Log
    # Dedicated logger that does not propagate to root, ensuring audit logs are written ONLY to audit.log
    audit_logger = logging.getLogger("rag_system.audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    
    # Clear any existing handlers
    for h in audit_logger.handlers[:]:
        audit_logger.removeHandler(h)

    audit_handler = logging.FileHandler(os.path.join(log_dir, "audit.log"), encoding="utf-8")
    audit_handler.setFormatter(json_formatter)
    audit_logger.addHandler(audit_handler)

    logging.getLogger("rag_system").info(
        f"Structured JSON logging initialized. Console level: {log_level_str} | Target files: logs/"
    )
