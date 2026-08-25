export type SimulationHandle = { simulation_id: string; status: "completed"; passed: boolean };

export class SimulationClient {
  constructor(private readonly baseUrl: string) {}

  private async request(path: string, init?: RequestInit): Promise<unknown> {
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
    });
    if (!response.ok) throw new Error(`R1 simulation API ${response.status}`);
    return response.json();
  }

  compile(design: unknown): Promise<unknown> {
    return this.request("/v1/compile", { method: "POST", body: JSON.stringify(design) });
  }

  simulate(trajectory: unknown): Promise<SimulationHandle> {
    return this.request("/v1/simulations", { method: "POST", body: JSON.stringify(trajectory) }) as Promise<SimulationHandle>;
  }

  report(simulationId: string): Promise<unknown> {
    return this.request(`/v1/simulations/${encodeURIComponent(simulationId)}/report`);
  }

  preview(simulationId: string): Promise<unknown> {
    return this.request(`/v1/simulations/${encodeURIComponent(simulationId)}/preview`);
  }
}

export async function sha256Hex(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}
