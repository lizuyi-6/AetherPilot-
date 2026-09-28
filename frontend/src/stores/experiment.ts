import { defineStore } from "pinia";
import { api, wsUrl } from "../api/client";
import type {
  AetherEvent, Approval, ExperimentDetail, Incident, TelemetrySample,
} from "../types";

interface TrainingPoint { ts: number; step: number; loss: number | null; lr: number | null }

// Long experiments stream thousands of events/points over WS; cap the in-memory
// buffers so a multi-hour run cannot grow them without bound.
const MAX_EVENTS = 2000;
const MAX_TRAINING_POINTS = 3000;

export const useExperimentStore = defineStore("experiment", {
  state: () => ({
    detail: null as ExperimentDetail | null,
    events: [] as AetherEvent[],
    incidents: [] as Incident[],
    approvals: [] as Approval[],
    progress: { step: 0, maxSteps: 0, loss: null as number | null, lr: null as number | null },
    trainingSeries: [] as TrainingPoint[],
    activeIncident: null as AetherEvent | null,
    lastRecoveryPlan: null as AetherEvent | null,
    integrity: null as AetherEvent | null,
    report: null as string | null,
    ws: null as WebSocket | null,
  }),
  getters: {
    pendingApprovals(state): Approval[] {
      return state.approvals.filter((a) => a.status === "PENDING");
    },
    isTerminal(state): boolean {
      return ["COMPLETED", "FAILED", "CANCELLED"].includes(state.detail?.state ?? "");
    },
  },
  actions: {
    async load(id: string) {
      this.detail = await api.experiment(id);
      this.events = await api.events(id);
      this.incidents = await api.incidents(id);
      this.approvals = await api.approvals(id);
      this._rebuildDerived();
      if (this.detail.state === "COMPLETED") {
        try {
          this.report = (await api.report(id)).markdown;
        } catch { /* report may not exist yet */ }
      }
    },
    connect(id: string) {
      this.disconnect();
      const ws = new WebSocket(wsUrl(`/ws/experiments/${id}`));
      this.ws = ws;
      ws.onmessage = async (msg) => {
        const event = JSON.parse(msg.data) as AetherEvent;
        this.events.push(event);
        if (this.events.length > MAX_EVENTS) this.events.splice(0, this.events.length - MAX_EVENTS);
        this._applyEvent(id, event);
      };
      ws.onclose = () => {
        if (!this.isTerminal) setTimeout(() => this.connect(id), 3000);
      };
    },
    disconnect() {
      if (this.ws) {
        this.ws.onclose = null;
        this.ws.close();
        this.ws = null;
      }
    },
    async decide(approvalId: string, decision: "approve" | "reject") {
      if (!this.detail) return;
      await api.decideApproval(this.detail.id, approvalId, decision);
      this.approvals = await api.approvals(this.detail.id);
    },
    _rebuildDerived() {
      this.trainingSeries = [];
      this.activeIncident = null;
      this.lastRecoveryPlan = null;
      this.integrity = null;
      this.progress = { step: 0, maxSteps: 0, loss: null, lr: null };
      for (const e of this.events) this._applyDerived(e);
    },
    _applyEvent(id: string, e: AetherEvent) {
      this._applyDerived(e);
      if (e.type === "STATE_CHANGED" || e.type === "CONFIG_PATCH_APPLIED" || e.type === "EVALUATION_COMPLETED") {
        void api.experiment(id).then((d) => (this.detail = d));
      }
      if (e.type === "INCIDENT_DETECTED") {
        void api.incidents(id).then((i) => (this.incidents = i));
      }
      if (e.type === "APPROVAL_REQUESTED") {
        void api.approvals(id).then((a) => (this.approvals = a));
      }
      if (e.type === "EXPERIMENT_COMPLETED") {
        void api.report(id).then((r) => (this.report = r.markdown)).catch(() => undefined);
      }
    },
    _applyDerived(e: AetherEvent) {
      if (e.type === "TRAINING_PROGRESS") {
        const p = e.payload as { step?: number; max_steps?: number; loss?: number | string; lr?: number };
        const loss = typeof p.loss === "number" ? p.loss : null;
        this.progress = {
          step: p.step ?? this.progress.step,
          maxSteps: p.max_steps || this.progress.maxSteps || (this.detail?.config?.max_steps as number) || 0,
          loss,
          lr: p.lr ?? null,
        };
        this.trainingSeries.push({ ts: e.ts, step: p.step ?? 0, loss, lr: p.lr ?? null });
        if (this.trainingSeries.length > MAX_TRAINING_POINTS) {
          this.trainingSeries.splice(0, this.trainingSeries.length - MAX_TRAINING_POINTS);
        }
      }
      if (e.type === "INCIDENT_DETECTED") this.activeIncident = e;
      if (e.type === "RECOVERY_PLAN_CREATED") this.lastRecoveryPlan = e;
      if (e.type === "INTEGRITY_CHECKED") this.integrity = e;
      if (e.type === "RECOVERY_SUCCEEDED" || e.type === "TRAINING_RESUMED") {
        this.activeIncident = null;
        this.lastRecoveryPlan = null;
      }
    },
  },
});

export type { TelemetrySample };
