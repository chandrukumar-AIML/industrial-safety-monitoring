"""
scripts/load_test.py

Locust load test — measures p95 latency and error rate for the API.

Usage:
    pip install locust
    locust -f scripts/load_test.py --host=http://localhost:8000 \
      --users=50 --spawn-rate=5 --run-time=2m --headless \
      --csv=results/perf_$(date +%Y%m%d)

Endpoints covered:
    GET  /health                  — baseline
    GET  /violations              — DB read
    GET  /analytics/summary       — aggregation query
    POST /chat                    — RAG + LLM (heaviest)
"""

import random

from locust import HttpUser, between, task

_CHAT_QUERIES = [
    "What are OSHA requirements for hard hats?",
    "How many violations occurred today?",
    "Which zone has the highest risk score?",
    "What PPE is required for welding areas?",
    "Show me the compliance rate for this week.",
]

API_KEY = "demo-admin-key"  # matches demo_seed.py / ADMIN_API_KEY env var


class SafetyAPIUser(HttpUser):
    """Simulates a dashboard user hitting the most common endpoints."""

    wait_time = between(0.5, 2.0)

    def on_start(self):
        self.headers = {"Authorization": f"Bearer {API_KEY}"}

    @task(5)
    def get_violations(self):
        self.client.get("/violations?limit=25", headers=self.headers, name="/violations")

    @task(3)
    def get_analytics(self):
        self.client.get("/analytics/summary", headers=self.headers, name="/analytics/summary")

    @task(2)
    def get_health(self):
        self.client.get("/health", name="/health")

    @task(2)
    def get_workers(self):
        self.client.get("/workers?limit=10", headers=self.headers, name="/workers")

    @task(1)
    def post_chat(self):
        query = random.choice(_CHAT_QUERIES)
        self.client.post(
            "/chat",
            json={"message": query},
            headers=self.headers,
            name="/chat",
            timeout=30,
        )

    @task(1)
    def get_sites(self):
        self.client.get("/sites", headers=self.headers, name="/sites")
