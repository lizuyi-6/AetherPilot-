import { defineStore } from "pinia";
import { api, wsUrl } from "../api/client";
import type { SystemStatus, TelemetrySample } from "../types";

export const useSystemStore = defineStore("system", {
  state: () => ({
    status: null as SystemStatus | null,
    telemetry: [] as TelemetrySample[],
    wsConnected: false,
    error: null as string | null,
  }),
  getters: {
    healthy(state): boolean {
      return !!state.status && state.error === null;
    },
    gpuLabel(state): string {
      const g = state.status?.gpu;
      if (!g) return "…";
      return g.available ? (g.gpus[0]?.name ?? "GPU") : "GPU UNAVAILABLE";
    },
  },
  actions: {
    async refresh() {
      try {
        this.status = await api.systemStatus();
        this.error = null;
      } catch (e) {
        this.error = String(e);
      }
    },
    connectWs() {
      const connect = () => {
        const ws = new WebSocket(wsUrl("/ws/system"));
        ws.onopen = () => (this.wsConnected = true);
        ws.onclose = () => {
          this.wsConnected = false;
          setTimeout(connect, 3000);
        };
        ws.onmessage = (msg) => {
          const parsed = JSON.parse(msg.data) as { type: string; data: TelemetrySample };
          if (parsed.type === "telemetry") {
            this.telemetry.push(parsed.data);
            if (this.telemetry.length > 300) this.telemetry.shift();
          }
        };
      };
      connect();
    },
  },
});
