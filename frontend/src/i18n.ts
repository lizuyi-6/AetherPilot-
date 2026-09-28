/* Minimal i18n scaffold: English default, 简体中文 available. */

import { reactive } from "vue";

type Lang = "en" | "zh";

const dict: Record<string, { en: string; zh: string }> = {
  tagline: { en: "Autonomous Experiment Operator", zh: "自主实验操作员" },
  systemHealth: { en: "SYSTEM HEALTH", zh: "系统状态" },
  healthy: { en: "HEALTHY", zh: "正常" },
  degraded: { en: "DEGRADED", zh: "降级" },
  whatRun: { en: "What should we run?", zh: "要运行什么实验？" },
  planExperiment: { en: "PLAN EXPERIMENT", zh: "规划实验" },
  mission: { en: "MISSION", zh: "任务" },
  agentActions: { en: "AGENT ACTIONS", zh: "Agent 行为" },
  incidents: { en: "INCIDENTS", zh: "故障" },
  integrity: { en: "EXPERIMENT INTEGRITY", zh: "实验完整性" },
  demoWorkload: { en: "DEMO WORKLOAD — Controlled Fault Injection", zh: "演示负载 — 受控故障注入" },
  live: { en: "LIVE", zh: "实时" },
  approve: { en: "APPROVE", zh: "批准" },
  reject: { en: "REJECT", zh: "拒绝" },
  approvalRequired: { en: "APPROVAL REQUIRED", zh: "需要人工批准" },
  stop: { en: "STOP", zh: "停止" },
  viewReport: { en: "VIEW REPORT", zh: "查看报告" },
  scenarios: { en: "SCENARIOS", zh: "场景" },
  recentExperiments: { en: "RECENT EXPERIMENTS", zh: "最近实验" },
  skills: { en: "SKILLS", zh: "技能" },
  home: { en: "HOME", zh: "首页" },
};

export const i18n = reactive({
  lang: "en" as Lang,
  toggle() {
    this.lang = this.lang === "en" ? "zh" : "en";
  },
});

export function t(key: keyof typeof dict | string): string {
  const entry = dict[key];
  if (!entry) return key;
  return entry[i18n.lang];
}
