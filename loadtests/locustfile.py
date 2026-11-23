"""Run with: locust -f loadtests/locustfile.py --host http://localhost:8000"""
import os
import random
from locust import HttpUser, between, task, tag

API_KEY = os.getenv("IATM_API_KEY", "")

class NormalTraffic(HttpUser):
    wait_time = between(0.2, 1.2)

    def on_start(self):
        self.client.headers.update({"X-API-Key": API_KEY} if API_KEY else {})

    @task(5)
    @tag("normal")
    def alpha_read(self):
        self.client.get("/alpha/catalog/items?limit=10", name="/alpha/catalog/items")

    @task(2)
    @tag("normal")
    def beta_read(self):
        self.client.get("/beta/search?q=traffic", name="/beta/search")

    @task(1)
    @tag("normal")
    def alpha_write(self):
        self.client.post("/alpha/orders", json={"sku": "demo", "quantity": 1}, name="/alpha/orders")

class BotTraffic(HttpUser):
    wait_time = between(0.01, 0.08)
    weight = 1

    def on_start(self):
        self.client.headers.update({"X-API-Key": API_KEY} if API_KEY else {})

    @task
    @tag("bot", "attack")
    def enumerate(self):
        self.client.get(f"/alpha/login?user=admin&attempt={random.randrange(100000)}", name="/alpha/login [bot]")

class FlashCrowd(HttpUser):
    wait_time = between(0.0, 0.03)
    weight = 1

    @task
    @tag("flash-crowd", "spike")
    def campaign(self):
        self.client.get("/beta/campaign/sale", name="/beta/campaign/sale [spike]")
