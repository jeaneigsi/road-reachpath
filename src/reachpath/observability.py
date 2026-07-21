from __future__ import annotations

from prometheus_client import Counter, Histogram, generate_latest


HTTP_REQUESTS = Counter(
    "reachpath_http_requests_total",
    "Total HTTP requests handled by ReachPath",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "reachpath_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "route"),
)
RESEARCH_RUNS = Counter(
    "reachpath_research_runs_total",
    "Research runs by final state",
    ("status",),
)
CRM_SYNCS = Counter(
    "reachpath_crm_syncs_total",
    "CRM contact synchronizations by outcome",
    ("provider", "status"),
)


def metrics_payload() -> bytes:
    return generate_latest()
