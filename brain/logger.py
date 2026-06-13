import logging
import sys
import json
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    """Structured JSON formatter."""
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        # Default to JSON formatter if in production, or simple one for dev
        # For now, let's use a standard format and allow overriding
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

def configure_logging(level=logging.INFO, use_json=False):
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    
    handler = logging.StreamHandler(sys.stdout)
    if use_json:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(level)
