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
  origin?: ContentOrigin;
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
  origin?: ContentOrigin;
  provenance?: ContentProvenance[];
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
  origin?: ContentOrigin;
  provenance?: ContentProvenance[];
  media?: CatalogMedia[];
}

export interface CatalogComponentListResponse {
  items: CatalogComponent[];
  total: number;
}

export type ContentOrigin = "manual" | "imported" | "mixed";

export interface SourceAttribution {
  sourceName: string;
  sourceUrl: string;
  sourceDomain: string;
  originalTitle?: string;
  originalAuthor?: string;
  originalPublishedAt?: string;
  importedAt: string;
  lastCheckedAt?: string;
  sourceLanguage?: string;
  contentLicense?: string;
  attributionText?: string;
}

export interface ContentProvenance {
  id: string;
  contentType:
    | "description"
    | "specification"
    | "image"
    | "diagram"
    | "code"
    | "video"
    | "document";
  source: SourceAttribution;
  fieldName?: string;
  mediaId?: string;
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
