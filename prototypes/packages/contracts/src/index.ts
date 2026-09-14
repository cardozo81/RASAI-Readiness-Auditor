export type Status = 'healthy' | 'running' | 'queued' | 'warning' | 'failed' | 'success' | 'paused' | 'scheduled' | 'partial';
export type Role = 'OWNER' | 'ADMIN' | 'ANALYST' | 'OPERATOR' | 'VIEWER';
export type CredentialSource = 'PLATFORM_SHARED' | 'ORGANIZATION_SHARED' | 'USER_PRIVATE';
export type CredentialStatus = 'ACTIVE' | 'DEGRADED' | 'DISABLED' | 'INVALID';

export interface TenantContext {
  organizationId: string;
  workspaceId: string;
  projectId: string;
  propertyId: string;
  environmentId: string;
}

export interface UserIdentity {
  userId: string;
  name: string;
  email: string;
  role: Role;
  organizationName: string;
}

export interface Metric {
  label: string;
  value: string;
  trend?: string;
  tone?: 'neutral' | 'positive' | 'warning' | 'danger' | 'info';
  hint?: string;
}

export interface ExecutionStage {
  id: string;
  label: string;
  status: 'done' | 'running' | 'pending' | 'failed';
  completedUnits?: number;
  totalUnits?: number;
}

export interface ExecutionProgress {
  jobId: string;
  percent: number;
  currentStage: string;
  message: string;
  stages: ExecutionStage[];
  updatedAt: string;
}

export interface ExecutionJob {
  jobId: string;
  projectId: string;
  propertyId: string;
  environmentId: string;
  jobType: 'AUDIT' | 'SEARCH_MONITOR' | 'REPORT_REFRESH';
  title: string;
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' | 'PARTIAL';
  requestedBy: string;
  origin: 'MANUAL' | 'SCHEDULE';
  priority: number;
  startedAt?: string;
  completedAt?: string;
  scheduledFor?: string;
  auditId?: string;
  progress?: ExecutionProgress;
}

export interface Schedule {
  scheduleId: string;
  projectId: string;
  name: string;
  jobType: 'AUDIT' | 'SEARCH_MONITOR' | 'REPORT_REFRESH';
  recurrenceLabel: string;
  timezone: string;
  overlapPolicy: 'SKIP' | 'QUEUE';
  status: 'ACTIVE' | 'PAUSED' | 'DISABLED';
  nextRunAt?: string;
  lastRunStatus?: string;
}

export interface AuditSummary {
  auditId: string;
  projectName: string;
  propertyName: string;
  status: 'SUCCESS' | 'PARTIAL' | 'FAILED';
  eventTime: string;
  urlCount: number;
  devices: string[];
  sari: number;
  geo: number;
  apdex: number;
  reports: number;
}

export interface CredentialReference {
  credentialId: string;
  label: string;
  provider: string;
  source: CredentialSource;
  ownerLabel: string;
  status: CredentialStatus;
  configured: boolean;
  lastUsedAt?: string;
  consumers?: number;
  secretPreview?: never;
}

export interface UsageEvent {
  eventId: string;
  organizationId: string;
  organizationName: string;
  userId: string;
  userName: string;
  projectId: string;
  projectName: string;
  jobId: string;
  auditId?: string;
  reportId?: string;
  provider: string;
  model?: string;
  operation: string;
  credentialId: string;
  credentialSource: CredentialSource;
  status: 'SUCCESS' | 'FAILED' | 'TIMEOUT';
  quantity: number;
  inputTokens?: number;
  outputTokens?: number;
  providerCostEstimate: number;
  platformCost: number;
  billableCost: number;
  currency: 'USD';
  occurredAt: string;
}

export interface ClientAccount {
  organizationId: string;
  name: string;
  plan: string;
  users: number;
  projects: number;
  activeJobs: number;
  monthlyPlatformCost: number;
  monthlyBillable: number;
  status: 'ACTIVE' | 'ATTENTION' | 'SUSPENDED';
}

export interface ConfigValue {
  key: string;
  label: string;
  category: string;
  value: string | number | boolean;
  origin: 'SYSTEM' | 'ORGANIZATION' | 'PROJECT' | 'PROPERTY' | 'ENVIRONMENT' | 'TEMPLATE' | 'JOB';
  scopeLabel: string;
  overridden: boolean;
  secret: boolean;
  editable: boolean;
}

export interface ReportSummary {
  reportId: string;
  auditId: string;
  name: string;
  type: string;
  status: 'READY' | 'PARTIAL' | 'FAILED';
  generatedAt: string;
  source: 'CORE' | 'AI' | 'CONSOLIDATED';
}

export interface SaasClientContract {
  currentUser(): Promise<UserIdentity>;
  clientDashboard(): Promise<{ metrics: Metric[]; jobs: ExecutionJob[]; schedules: Schedule[]; audits: AuditSummary[] }>;
  executionJobs(): Promise<ExecutionJob[]>;
  executionJob(jobId: string): Promise<ExecutionJob | undefined>;
  schedules(): Promise<Schedule[]>;
  audits(): Promise<AuditSummary[]>;
  reports(): Promise<ReportSummary[]>;
  credentials(): Promise<CredentialReference[]>;
  effectiveConfig(): Promise<ConfigValue[]>;
  clients(): Promise<ClientAccount[]>;
  usage(): Promise<UsageEvent[]>;
  platformCredentials(): Promise<CredentialReference[]>;
  platformDefaults(): Promise<ConfigValue[]>;
}

export const contractGaps = [
  'ExecutionProgress detalhado por etapa/unidades',
  'CredentialReference e credential source/owner',
  'Separação provider/platform/billable cost',
  'Backoffice global fora da tenancy normal de cliente',
  'Defaults hierárquicos com origem/herança/override',
  'Catálogo estruturado de reports e drill-down',
] as const;
