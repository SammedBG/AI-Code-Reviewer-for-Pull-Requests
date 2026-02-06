"""
Structured Logging Configuration

This module sets up production-ready structured logging using structlog.
Logs are formatted as JSON in production for easy parsing by log aggregators.

Design Decisions:
- Use structlog for structured, contextual logging
- JSON format in production, colored console in development
- Add request context (correlation IDs) to all logs
- Never log sensitive data (keys, tokens, secrets)
"""

import logging
import sys
from typing import Any, Dict

import structlog
from structlog.types import EventDict, WrappedLogger

from app.config import get_settings


def filter_sensitive_data(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Processor to filter out sensitive data from logs.
    
    This is a critical security measure to prevent accidental
    exposure of secrets, tokens, and API keys in logs.
    """
    sensitive_keys = {
        "token", "access_token", "api_key", "apikey", "secret",
        "password", "private_key", "authorization", "auth",
        "credential", "jwt", "bearer"
    }
    
    def redact_dict(d: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively redact sensitive values in a dict."""
        result = {}
        for key, value in d.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                result[key] = "[REDACTED]"
            elif isinstance(value, dict):
                result[key] = redact_dict(value)
            elif isinstance(value, str) and len(value) > 20:
                # Check if value looks like a token/key
                if value.startswith(("sk-", "ghp_", "ghs_", "github_pat_")):
                    result[key] = "[REDACTED]"
                else:
                    result[key] = value
            else:
                result[key] = value
        return result
    
    return redact_dict(event_dict)


def add_app_context(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add application context to every log entry."""
    event_dict["app"] = "ai-pr-reviewer"
    event_dict["version"] = "1.0.0"
    return event_dict


def setup_logging() -> None:
    """
    Configure structured logging for the application.
    
    This function should be called once at application startup.
    It configures both structlog and the standard logging library.
    """
    settings = get_settings()
    
    # Determine if we're in production mode (JSON logging)
    use_json = settings.log_json_format
    
    # Common processors for all modes
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        add_app_context,
        filter_sensitive_data,
    ]
    
    if use_json:
        # Production: JSON format for log aggregators
        structlog.configure(
            processors=shared_processors + [
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    else:
        # Development: Colored console output
        structlog.configure(
            processors=shared_processors + [
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
        )
    
    # Configure root logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, settings.log_level))
    
    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a logger instance with the given name.
    
    Usage:
        logger = get_logger(__name__)
        logger.info("Processing PR", pr_number=123, repo="owner/repo")
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)
