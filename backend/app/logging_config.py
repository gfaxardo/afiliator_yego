"""
Logging configuration for AFILIATOR production.

Configura loggers con formato estructurado simple.
NO loggea secretos.
"""
import logging
import sys


def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove default handlers
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root.addHandler(handler)

    # Silence noisy libraries
    for lib in ("uvicorn.access", "sqlalchemy.engine", "passlib"):
        logging.getLogger(lib).setLevel(logging.WARNING)
