"""HTTP client for compile, simulation, reports and previews."""

import httpx


class SimulationClient:
    def __init__(self, base_url: str, *, timeout_s: float = 30) -> None:
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s)

    def compile(self, design: dict) -> dict:
        response = self.client.post("/v1/compile", json=design)
        response.raise_for_status()
        return response.json()

    def simulate(self, trajectory: dict) -> dict:
        response = self.client.post("/v1/simulations", json=trajectory)
        response.raise_for_status()
        return response.json()

    def simulation(self, simulation_id: str) -> dict:
        response = self.client.get(f"/v1/simulations/{simulation_id}")
        response.raise_for_status()
        return response.json()

    def report(self, simulation_id: str) -> dict:
        response = self.client.get(f"/v1/simulations/{simulation_id}/report")
        response.raise_for_status()
        return response.json()

    def preview(self, simulation_id: str) -> dict:
        response = self.client.get(f"/v1/simulations/{simulation_id}/preview")
        response.raise_for_status()
        return response.json()
