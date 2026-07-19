export type Role = "student" | "teacher" | "administrator";

export interface User {
  id: string;
  login: string;
  display_name: string;
  roles: Role[];
}

export interface LoginInput {
  login: string;
  password: string;
}

export interface LoginResponse {
  user: User;
  expires_at: string;
}

export interface LogoutResponse {
  status: "logged_out";
}

export interface CreateUserInput {
  login: string;
  display_name: string;
  password: string;
  roles: Role[];
}

export interface MutationResponse {
  status: string;
}

export type JobStatus = "queued" | "running" | "retrying" | "succeeded" | "failed";
export type MediaKind = "image" | "video";

export interface BackgroundJob {
  id: string;
  asset_id: string;
  owner_user_id: string;
  kind: MediaKind;
  queue_name: string;
  task_name: string;
  status: JobStatus;
  phase: string;
  progress_percent: number;
  attempts: number;
  max_attempts: number;
  manual_retry_count: number;
  error_code: string | null;
  next_retry_at: string | null;
  heartbeat_at: string | null;
  last_enqueued_at: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface BackgroundJobListResponse {
  items: BackgroundJob[];
  total: number;
  limit: number;
  offset: number;
}

export interface JobMutationResponse {
  id: string;
  status: "queued";
}

export interface ApiErrorBody {
  detail?: {
    code?: string;
    [key: string]: unknown;
  };
}

export type ComponentStatus = "draft" | "published" | "archived";
export type Difficulty = "beginner" | "intermediate" | "advanced";
export type CodeExampleVisibility = "student" | "teacher";

export interface Category {
  id: string;
  slug: string;
  name: string;
}

export interface TechnicalSpecificationInput {
  key: string;
  label: string;
  value_text: string;
  value_number: string | null;
  unit: string | null;
}

export interface TechnicalSpecification extends TechnicalSpecificationInput {
  position: number;
}

export type CompatibilityTarget = "board" | "library" | "platform";

export interface ComponentCompatibilityInput {
  target_type: CompatibilityTarget;
  name: string;
  version_constraint: string | null;
  notes: string | null;
}

export interface ComponentCompatibility extends ComponentCompatibilityInput {
  position: number;
}

export interface CodeExampleInput {
  title: string;
  language: string;
  practical_task: string;
  hints: string[];
  body: string;
  libraries: string[];
  explanation: string | null;
  visibility: CodeExampleVisibility;
}

export interface CodeExample extends CodeExampleInput {
  position: number;
}

export interface ComponentSummary {
  id: string;
  slug: string;
  status: ComponentStatus;
  title: string;
  summary: string;
  primary_category: Category;
  revision: number;
  updated_at: string;
  sources: SourceSnapshot[];
}

export interface ComponentListResponse {
  items: ComponentSummary[];
  total: number;
}

export interface ComponentCard extends ComponentSummary {
  aliases: string[];
  manufacturer: string | null;
  model: string | null;
  primary_category_id: string;
  tags: string[];
  description: string;
  purpose: string | null;
  usage_notes: string | null;
  safety_notes: string | null;
  difficulty: Difficulty;
  teacher_notes: string | null;
  manual_original: boolean;
  published_at: string | null;
  specifications: TechnicalSpecification[];
  compatibility: ComponentCompatibility[];
  code_examples: CodeExample[];
  media?: CatalogMedia[];
}

export interface ComponentDraftInput {
  slug: string;
  title: string;
  aliases: string[];
  manufacturer: string | null;
  model: string | null;
  primary_category_id: string;
  tags: string[];
  summary: string;
  description: string;
  purpose: string | null;
  usage_notes: string | null;
  safety_notes: string | null;
  difficulty: Difficulty;
  teacher_notes: string | null;
  manual_original: boolean;
  specifications: TechnicalSpecificationInput[];
  compatibility: ComponentCompatibilityInput[];
  code_examples: CodeExampleInput[];
}

export interface ComponentUpdateInput extends ComponentDraftInput {
  revision: number;
}

export interface LifecycleInput {
  revision: number;
}

export interface CatalogComponent {
  id: string;
  slug: string;
  title: string;
  summary: string;
  primary_category: Category;
  aliases: string[];
  manufacturer: string | null;
  model: string | null;
  tags: string[];
  description: string;
  purpose: string | null;
  usage_notes: string | null;
  safety_notes: string | null;
  difficulty: Difficulty;
  published_at: string;
  specifications: TechnicalSpecification[];
  compatibility: ComponentCompatibility[];
  code_examples: CodeExample[];
  sources: SourceSnapshot[];
  media?: CatalogMedia[];
}

export interface CatalogComponentListResponse {
  items: CatalogComponent[];
  total: number;
}

export interface SourceSnapshot {
  display_name: string;
  original_url: string | null;
  repository_url: string | null;
  license_name: string;
  license_spdx: string;
  license_url: string;
  source_revision: string;
  source_tag: string | null;
  source_file_path: string | null;
  source_entry_name: string | null;
  modifications_notice: string;
  imported_at: string;
  attribution: string;
  parser_name: string;
  parser_version: string;
}

export interface CatalogSource {
  key: string;
  display_name: string;
  repository_url: string | null;
  source_type: string;
  status: "active" | "inactive" | "disabled";
  content_policy: string;
  license_name: string | null;
  license_spdx: string | null;
  license_url: string | null;
  attribution_template: string | null;
  adapter_version: string;
  default_revision_policy: string;
  disable_reason: string | null;
}

export type RepositorySourceKey = "seeed_wiki" | "kicad_symbols";

export interface RepositoryImportInput {
  source_key: RepositorySourceKey;
  revision: string;
  file_path: string;
  entry_name: string | null;
}

export interface RepositoryFile {
  file_path: string;
  size: number | null;
}

export interface RepositoryDiscoveryResponse {
  source_key: RepositorySourceKey;
  repository_url: string;
  revision: string;
  files_scanned: number;
  files: RepositoryFile[];
}

export interface RepositoryEntry {
  file_path: string;
  entry_name: string | null;
  title: string | null;
}

export interface RepositoryEntryDiscoveryResponse {
  source_key: RepositorySourceKey;
  repository_url: string;
  revision: string;
  entries: RepositoryEntry[];
}

export interface FieldProvenanceSnapshot {
  repository_url: string;
  source_revision: string;
  source_file_path: string;
  section_or_property: string;
  confidence: "high" | "medium" | "low";
  transformation: string;
}

export interface RepositoryPreview {
  source_key: RepositorySourceKey;
  repository_url: string;
  requested_revision: string;
  revision: string;
  file_path: string;
  entry_name: string | null;
  original_url: string;
  parser_name: string;
  parser_version: string;
  parse_status: string;
  warnings: string[];
  normalized_fields: Record<string, unknown>;
  provenance: Record<string, FieldProvenanceSnapshot[]>;
  license: { name: string; spdx: string; url: string; attribution: string };
  modifications_notice: string;
  draft_status: "draft";
}

export interface ImportJob {
  id: string;
  submitted_url: string;
  canonical_url: string | null;
  status: JobStatus;
  attempts: number;
  max_attempts: number;
  parser_version: string | null;
  draft_component_id: string | null;
  error_code: string | null;
  repository_url: string | null;
  requested_revision: string | null;
  source_revision: string | null;
  source_file_path: string | null;
  source_entry_name: string | null;
  parser_name: string | null;
  parse_status: string | null;
  warnings_json: string[];
  heartbeat_at: string | null;
  metrics_json: Record<string, unknown>;
}

export interface MediaSource {
  sourceName: string;
  sourceUrl: string;
  originalMediaUrl?: string;
  originalAuthor?: string;
  contentLicense?: string;
  importedAt: string;
}

export interface CatalogMedia {
  id: string;
  kind: "image" | "video";
  alt: string;
  thumbnailUrl?: string;
  processedUrl?: string;
  originalUrl?: string;
  posterUrl?: string;
  source?: MediaSource;
}

export type DuplicateDecision = "merge" | "attach" | "create" | "reject";

export interface DuplicateCandidate {
  id: string;
  kind: "exact" | "fuzzy";
  status: "open" | "merged" | "rejected" | "superseded";
  score: number;
  algorithm_version: string;
  evidence: Record<string, unknown>;
  created_at: string;
  left: ComponentCard;
  right: ComponentCard;
}

export interface DuplicateCandidateListResponse {
  items: DuplicateCandidate[];
  total: number;
}

export interface DuplicateDecisionInput {
  decision: DuplicateDecision;
  left_revision: number;
  right_revision: number;
  survivor_component_id: string | null;
  field_sources: Record<string, string>;
  reason: string;
}

export interface DuplicateDecisionResponse {
  id: string;
  candidate_id: string;
  decision: DuplicateDecision;
  decided_at: string;
}
