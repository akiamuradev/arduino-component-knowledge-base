import type {
  ApiErrorBody,
  BackgroundJobListResponse,
  CatalogSource,
  CatalogComponent,
  CatalogComponentListResponse,
  Category,
  ComponentCard,
  ComponentDraftInput,
  ComponentListResponse,
  ComponentStatus,
  ComponentUpdateInput,
  CreateUserInput,
  DuplicateCandidate,
  DuplicateCandidateListResponse,
  DuplicateDecisionInput,
  DuplicateDecisionResponse,
  LoginInput,
  LoginResponse,
  LogoutResponse,
  MutationResponse,
  JobMutationResponse,
  JobStatus,
  ImportJob,
  RepositoryDiscoveryResponse,
  RepositoryEntryDiscoveryResponse,
  RepositoryImportInput,
  RepositoryPreview,
  Role,
  User,
} from "./contracts";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

if (!configuredBaseUrl.startsWith("/") || configuredBaseUrl.startsWith("//")) {
  throw new Error("VITE_API_BASE_URL must be a same-origin absolute path");
}

const API_BASE_URL = configuredBaseUrl.replace(/\/$/, "");
const CSRF_COOKIE = "ackb_csrf";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly details?: Readonly<Record<string, unknown>>,
    message = "API request failed",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function readCookie(name: string): string | undefined {
  const prefix = `${encodeURIComponent(name)}=`;
  const pair = document.cookie
    .split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith(prefix));
  if (pair === undefined) {
    return undefined;
  }
  try {
    return decodeURIComponent(pair.slice(prefix.length));
  } catch {
    return undefined;
  }
}

async function responseBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return undefined;
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return undefined;
  }
  return response.json() as Promise<unknown>;
}

function errorCode(body: unknown): string {
  if (typeof body !== "object" || body === null) {
    return "request_failed";
  }
  const candidate = body as ApiErrorBody;
  return typeof candidate.detail?.code === "string"
    ? candidate.detail.code
    : "request_failed";
}

function errorDetails(body: unknown): Readonly<Record<string, unknown>> | undefined {
  if (typeof body !== "object" || body === null) {
    return undefined;
  }
  const detail = (body as ApiErrorBody).detail;
  return detail;
}

interface RequestOptions extends RequestInit {
  csrf?: boolean;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (options.csrf === true) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf === undefined) {
      throw new ApiError(403, "csrf_token_missing", undefined, "CSRF token is missing");
    }
    headers.set("X-CSRF-Token", csrf);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  const body = await responseBody(response);
  if (!response.ok) {
    throw new ApiError(response.status, errorCode(body), errorDetails(body));
  }
  return body as T;
}

export const api = {
  currentUser: (): Promise<User> => apiRequest<User>("/auth/me"),
  login: (input: LoginInput): Promise<LoginResponse> =>
    apiRequest<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  logout: (): Promise<LogoutResponse> =>
    apiRequest<LogoutResponse>("/auth/logout", { method: "POST", csrf: true }),
  createUser: (input: CreateUserInput): Promise<User> =>
    apiRequest<User>("/admin/users", {
      method: "POST",
      body: JSON.stringify(input),
      csrf: true,
    }),
  setRoles: (userId: string, roles: Role[]): Promise<MutationResponse> =>
    apiRequest<MutationResponse>(`/admin/users/${encodeURIComponent(userId)}/roles`, {
      method: "PUT",
      body: JSON.stringify({ roles }),
      csrf: true,
    }),
  disableUser: (userId: string): Promise<MutationResponse> =>
    apiRequest<MutationResponse>(`/admin/users/${encodeURIComponent(userId)}/disable`, {
      method: "POST",
      csrf: true,
    }),
  listJobs: (status?: JobStatus): Promise<BackgroundJobListResponse> => {
    const query = status === undefined ? "" : `?status=${encodeURIComponent(status)}`;
    return apiRequest<BackgroundJobListResponse>(`/admin/jobs${query}`);
  },
  retryJob: (jobId: string): Promise<JobMutationResponse> =>
    apiRequest<JobMutationResponse>(`/admin/jobs/${encodeURIComponent(jobId)}/retry`, {
      method: "POST",
      csrf: true,
    }),
  listWorkspaceComponents: (status?: ComponentStatus): Promise<ComponentListResponse> => {
    const query = status === undefined ? "" : `?status=${encodeURIComponent(status)}`;
    return apiRequest<ComponentListResponse>(`/workspace/components${query}`);
  },
  listWorkspaceCategories: (): Promise<Category[]> =>
    apiRequest<Category[]>("/workspace/categories"),
  getWorkspaceComponent: (componentId: string): Promise<ComponentCard> =>
    apiRequest<ComponentCard>(`/workspace/components/${encodeURIComponent(componentId)}`),
  createComponentDraft: (input: ComponentDraftInput): Promise<ComponentCard> =>
    apiRequest<ComponentCard>("/workspace/components", {
      method: "POST",
      body: JSON.stringify(input),
      csrf: true,
    }),
  updateComponentDraft: (
    componentId: string,
    input: ComponentUpdateInput,
  ): Promise<ComponentCard> =>
    apiRequest<ComponentCard>(`/workspace/components/${encodeURIComponent(componentId)}`, {
      method: "PUT",
      body: JSON.stringify(input),
      csrf: true,
    }),
  publishComponent: (componentId: string, revision: number): Promise<ComponentCard> =>
    apiRequest<ComponentCard>(`/workspace/components/${encodeURIComponent(componentId)}/publish`, {
      method: "POST",
      body: JSON.stringify({ revision }),
      csrf: true,
    }),
  archiveComponent: (componentId: string, revision: number): Promise<ComponentCard> =>
    apiRequest<ComponentCard>(`/workspace/components/${encodeURIComponent(componentId)}/archive`, {
      method: "POST",
      body: JSON.stringify({ revision }),
      csrf: true,
    }),
  listCatalogCategories: (): Promise<Category[]> => apiRequest<Category[]>("/catalog/categories"),
  listCatalogSources: (): Promise<CatalogSource[]> => apiRequest<CatalogSource[]>("/catalog/sources"),
  listCatalogComponents: (filters: {
    query?: string;
    categoryId?: string;
    difficulty?: string;
  }): Promise<CatalogComponentListResponse> => {
    const query = new URLSearchParams();
    if (filters.query !== undefined && filters.query.trim() !== "") query.set("q", filters.query.trim());
    if (filters.categoryId !== undefined && filters.categoryId !== "") query.set("category_id", filters.categoryId);
    if (filters.difficulty !== undefined && filters.difficulty !== "") query.set("difficulty", filters.difficulty);
    const suffix = query.size === 0 ? "" : `?${query.toString()}`;
    return apiRequest<CatalogComponentListResponse>(`/catalog/components${suffix}`);
  },
  getCatalogComponent: (slug: string): Promise<CatalogComponent> =>
    apiRequest<CatalogComponent>(`/catalog/components/${encodeURIComponent(slug)}`),
  discoverRepositoryFiles: (input: {
    sourceKey: RepositoryImportInput["source_key"];
    revision: string;
    query: string;
    limit?: number;
  }): Promise<RepositoryDiscoveryResponse> => {
    const query = new URLSearchParams({
      source_key: input.sourceKey,
      revision: input.revision,
      q: input.query,
      limit: String(input.limit ?? 25),
    });
    return apiRequest<RepositoryDiscoveryResponse>(`/import-jobs/repository/discovery?${query.toString()}`);
  },
  discoverRepositoryEntries: (input: {
    sourceKey: RepositoryImportInput["source_key"];
    revision: string;
    filePath: string;
    query?: string;
    limit?: number;
  }): Promise<RepositoryEntryDiscoveryResponse> => {
    const query = new URLSearchParams({
      source_key: input.sourceKey,
      revision: input.revision,
      file_path: input.filePath,
      limit: String(input.limit ?? 50),
    });
    if (input.query !== undefined && input.query.trim() !== "") query.set("q", input.query.trim());
    return apiRequest<RepositoryEntryDiscoveryResponse>(`/import-jobs/repository/entries?${query.toString()}`);
  },
  previewRepositoryImport: (input: RepositoryImportInput): Promise<RepositoryPreview> =>
    apiRequest<RepositoryPreview>("/import-jobs/repository/preview", {
      method: "POST",
      body: JSON.stringify(input),
      csrf: true,
    }),
  createRepositoryImport: (input: RepositoryImportInput, idempotencyKey: string): Promise<ImportJob> =>
    apiRequest<ImportJob>("/import-jobs/repository", {
      method: "POST",
      body: JSON.stringify(input),
      headers: { "Idempotency-Key": idempotencyKey },
      csrf: true,
    }),
  getImportJob: (jobId: string): Promise<ImportJob> =>
    apiRequest<ImportJob>(`/import-jobs/${encodeURIComponent(jobId)}`),
  listDuplicateCandidates: (): Promise<DuplicateCandidateListResponse> =>
    apiRequest<DuplicateCandidateListResponse>("/admin/duplicates?status=open"),
  getDuplicateCandidate: (candidateId: string): Promise<DuplicateCandidate> =>
    apiRequest<DuplicateCandidate>(`/admin/duplicates/${encodeURIComponent(candidateId)}`),
  decideDuplicate: (
    candidateId: string,
    input: DuplicateDecisionInput,
  ): Promise<DuplicateDecisionResponse> =>
    apiRequest<DuplicateDecisionResponse>(
      `/admin/duplicates/${encodeURIComponent(candidateId)}/decision`,
      { method: "POST", body: JSON.stringify(input), csrf: true },
    ),
};
