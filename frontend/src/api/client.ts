import type {
  Approval, AetherEvent, ExperimentDetail, ExperimentSummary,
  Incident, Scenario, SkillSummary, SystemStatus,
} from "../types";

const BASE = "";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status} ${path}: ${body}`);
  }
  return (await resp.json()) as T;
}

export const api = {
  systemStatus: () => req<SystemStatus>("/api/system/status"),
  scenarios: () => req<Scenario[]>("/api/scenarios"),
  skills: () => req<SkillSummary[]>("/api/skills"),
  experiments: () => req<ExperimentSummary[]>("/api/experiments"),
  experiment: (id: string) => req<ExperimentDetail>(`/api/experiments/${id}`),
  createExperiment: (body: unknown) =>
    req<{ id: string; contract: Contract_ }>("/api/experiments", { method: "POST", body: JSON.stringify(body) }),
  startExperiment: (id: string) => req(`/api/experiments/${id}/start`, { method: "POST" }),
  stopExperiment: (id: string) => req(`/api/experiments/${id}/stop`, { method: "POST" }),
  events: (id: string) => req<AetherEvent[]>(`/api/experiments/${id}/events`),
  incidents: (id: string) => req<Incident[]>(`/api/experiments/${id}/incidents`),
  approvals: (id: string) => req<Approval[]>(`/api/experiments/${id}/approvals`),
  decideApproval: (id: string, approvalId: string, decision: "approve" | "reject") =>
    req(`/api/experiments/${id}/approval/${approvalId}`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
  report: (id: string) => req<{ markdown: string }>(`/api/experiments/${id}/report`),
  pkg: (id: string) => req<{ manifest: Record<string, unknown>; workspace: string }>(`/api/experiments/${id}/package`),
};

interface Contract_ { experiment: { name: string } }

export function wsUrl(path: string): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}${path}`;
}
