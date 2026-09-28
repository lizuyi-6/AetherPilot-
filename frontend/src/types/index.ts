export interface GpuInfo {
  index: number;
  name: string;
  mem_total_mb: number;
  mem_used_mb: number;
  mem_free_mb: number;
  util_pct: number;
  temp_c: number | null;
  power_w: number | null;
}

export interface SystemStatus {
  host: { os: string; kernel: string; arch: string; python: string; cpu_count: number; ram_total_gb: number };
  gpu: {
    available: boolean;
    source: string;
    driver: string | null;
    cuda: string | null;
    detail: string;
    gpus: GpuInfo[];
  };
  cuda_toolkit: { nvcc: string | null; torch_cuda: string | null; torch_cuda_available: string | null };
  docker: { available: boolean; detail: string; nvidia_runtime: boolean };
  disk: { total_gb: number; free_gb: number };
  ram: { total_gb: number; used_gb: number };
  cpu_pct: number;
}

export interface TelemetrySample {
  ts: number;
  cpu_pct: number;
  ram_used_gb: number;
  ram_total_gb: number;
  disk_free_gb: number;
  gpu: { available: boolean; gpus: GpuInfo[] };
}

export interface ExperimentSummary {
  id: string;
  name: string;
  state: string;
  mode: string;
  created_at: number;
  updated_at: number;
  completed_at: number | null;
  recovery_attempts: number;
  integrity_status: string;
  best_checkpoint: string | null;
  error: string | null;
}

export interface ContractMetric { target: number; operator: string }
export interface Contract {
  experiment: { name: string };
  goal: { type: string; model: string; dataset: string | null; description: string };
  constraints: { max_vram_gb: number; max_duration_hours: number; max_disk_gb: number };
  permissions: Record<string, boolean | string>;
  metrics: Record<string, ContractMetric>;
  recovery: { allow_checkpoint_rollback: boolean; max_auto_recovery_attempts: number };
}

export interface ExperimentDetail extends ExperimentSummary {
  contract: Contract;
  config: Record<string, unknown>;
  original_config: Record<string, unknown>;
  final_metrics: {
    metrics?: Record<string, number | string>;
    targets?: Record<string, { target: number; operator: string; observed: unknown; pass: boolean }>;
    best_checkpoint?: string;
  };
  auto_changes: number;
  semantic_changes: number;
  workspace: string;
}

export interface AetherEvent {
  id: string;
  ts: number;
  experiment_id: string | null;
  type: string;
  message: string;
  severity: "info" | "warning" | "error";
  payload: Record<string, unknown>;
}

export interface Incident {
  id: string;
  ts: number;
  type: string;
  severity: string;
  status: string;
  evidence: string[];
  root_cause: string;
  confidence: number;
  recommended_actions: string[];
  recovery: {
    strategy?: string;
    config_patch?: Record<string, unknown>;
    resume_from_checkpoint?: string | null;
    integrity?: string;
  };
}

export interface Approval {
  id: string;
  ts: number;
  reason: string;
  status: string;
  action: { plan?: { strategy: string; config_patch: Record<string, unknown>; explanation: string } };
}

export interface SkillSummary {
  name: string;
  version: string;
  display_name: string;
  description: string;
  capabilities: { id: string; summary: string }[];
  permissions: Record<string, string>;
  detectors: { id: string; signature: string; severity: string }[];
  recovery_strategies: { id: string; for: string; patch: string; integrity: string }[];
  installed: boolean;
}

export interface Scenario {
  id: string;
  title: string;
  description: string;
  request: {
    name: string;
    goal: string;
    mode: "demo" | "real";
    demo: Record<string, unknown>;
    contract_overrides?: Record<string, unknown>;
  };
}
