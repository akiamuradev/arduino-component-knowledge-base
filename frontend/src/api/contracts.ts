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

export interface Category {
  id: string;
  slug: string;
  name: string;
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
}

export interface CatalogComponentListResponse {
  items: CatalogComponent[];
  total: number;
}
