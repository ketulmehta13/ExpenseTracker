"""Monitoring: Prometheus metrics and structured logs.

Metrics answer "how is it doing?" across all requests, scraped by Prometheus from GET /metrics:
- request counts by route and status, and latency histograms per route;
- what each ML feature did, e.g. where a category suggestion came from (history, model or
  none), whether help answered or declined, which assistant intents come up, and whether
  an LLM's output was used. A drop in model suggestions or a rise in declined help questions
  is visible here before anyone files a bug.

Logs answer "what happened in this request?": one JSON object per line. They never contain
what the user typed.
"""

from __future__ import annotations

import json
import logging
import time

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)


class Metrics:
    """One registry per app, so tests can build many apps without metric name clashes."""

    content_type = CONTENT_TYPE_LATEST

    def __init__(self):
        self.registry = registry = CollectorRegistry()
        self.requests = Counter(
            "ml_requests_total", "HTTP requests by route and status", ["route", "status"], registry=registry
        )
        self.latency = Histogram(
            "ml_request_seconds", "Request latency by route", ["route"],
            buckets=LATENCY_BUCKETS, registry=registry,
        )
        self.events = Counter(
            "ml_feature_events_total", "What each ML feature did", ["feature", "outcome"], registry=registry
        )

    def observe_request(self, route: str, status: int, seconds: float) -> None:
        self.requests.labels(route, str(status)).inc()
        self.latency.labels(route).observe(seconds)

    def event(self, feature: str, outcome: str) -> None:
        self.events.labels(feature, outcome).inc()

    def render(self) -> bytes:
        return generate_latest(self.registry)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging(level: str = "INFO") -> None:
    """Send the service's own loggers to stdout as JSON (uvicorn handles its own loggers)."""
    logger = logging.getLogger("ml_service")
    if not any(isinstance(handler.formatter, JsonFormatter) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
