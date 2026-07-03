"""
Structured JSON logging setup for production debugging and monitoring.

All log messages include:
- timestamp: When the event occurred
- level: DEBUG, INFO, WARNING, ERROR
- logger: Which component logged it
- message: Human-readable description
- node_id: Which node generated the log
- context: Relevant operational data (operation_id, key, duration, etc.)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs logs as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Convert log record to JSON string.
        
        Args:
            record: The log record from Python logging
            
        Returns:
            JSON-formatted string with all record details
        """
        # Extract node_id if available in record (added via LoggerAdapter)
        node_id = getattr(record, "node_id", "unknown")

        # Build base log entry with standard fields
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),  # ISO 8601 timestamp
            "level": record.levelname,  # DEBUG, INFO, WARNING, ERROR
            "logger": record.name,  # Component name (cache_node.app.routes, etc.)
            "message": record.getMessage(),  # The formatted log message
            "node_id": node_id,  # Which node in the cluster
        }

        # Add extra context fields if they exist in the record
        if hasattr(record, "context") and record.context:
            log_entry["context"] = record.context

        # Add exception info if this is an error with traceback
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry)


class ContextualLogger:
    """Wraps Python logger to add node_id and context to all messages."""

    def __init__(self, logger: logging.Logger, node_id: str):
        """Initialize contextual logger.
        
        Args:
            logger: Python logger instance
            node_id: ID of the current node (for all logs from this node)
        """
        self.logger = logger
        self.node_id = node_id

    def _log(
        self,
        level: int,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        *args,
        **kwargs,
    ):
        """Internal method to log with context.
        
        Args:
            level: Logging level (logging.DEBUG, logging.INFO, etc.)
            message: Log message
            context: Dict of contextual data to include in JSON
            *args: Additional arguments for format()
            **kwargs: Additional keyword arguments for logger
        """
        extra = {"node_id": self.node_id}
        if context:
            extra["context"] = context

        self.logger.log(level, message, *args, extra=extra, **kwargs)

    def debug(self, message: str, context: Optional[Dict] = None):
        """Log debug message with optional context."""
        self._log(logging.DEBUG, message, context)

    def info(self, message: str, context: Optional[Dict] = None):
        """Log info message with optional context."""
        self._log(logging.INFO, message, context)

    def warning(self, message: str, context: Optional[Dict] = None):
        """Log warning message with optional context."""
        self._log(logging.WARNING, message, context)

    def error(self, message: str, context: Optional[Dict] = None, exc_info=False):
        """Log error message with optional context and exception info."""
        self._log(logging.ERROR, message, context, exc_info=exc_info)


def setup_logging(node_id: str, log_level: str = "INFO") -> logging.Logger:
    """Configure structured JSON logging for the application.
    
    This sets up:
    - Console output with JSON formatting
    - Proper log level filtering
    - Node context tracking
    
    Args:
        node_id: ID of the current node
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        
    Returns:
        Configured logger instance
    """
    # Create root logger
    logger = logging.getLogger("cache_node")
    logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create console handler (output to stdout)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)

    # Apply JSON formatter to console handler
    formatter = JSONFormatter()
    console_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(console_handler)

    return logger


def get_contextual_logger(logger: logging.Logger, node_id: str) -> ContextualLogger:
    """Get a contextual logger that automatically adds node_id to all logs.
    
    Args:
        logger: Python logger instance
        node_id: ID of the current node
        
    Returns:
        ContextualLogger instance that adds node context automatically
    """
    return ContextualLogger(logger, node_id)
