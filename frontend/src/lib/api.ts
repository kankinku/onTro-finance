import type {
  AskResponse,
  CouncilCasesResponse,
  CouncilRetryResponse,
  DashboardSummary,
  EntityListResponse,
  GraphResponse,
  IngestDetail,
  IngestListResponse,
  IngestResult,
} from "./types";

const apiBase = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const buildUrl = (path: string, params?: Record<string, string | number | undefined>) => {
  const url = new URL(`${apiBase}${path}`, "http://local.console");

  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });

  return apiBase ? `${apiBase}${url.pathname}${url.search}` : `${url.pathname}${url.search}`;
};

const apiFetch = async <T>(path: string, init?: RequestInit, params?: Record<string, string | number | undefined>) => {
  const response = await fetch(buildUrl(path, params), {
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
    ...init,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new ApiError(message || "Request failed", response.status);
  }

  return (await response.json()) as T;
};

export const getDashboardSummary = () => apiFetch<DashboardSummary>("/api/dashboard/summary");

export const getIngests = (limit = 20) =>
  apiFetch<IngestListResponse>("/api/ingests", undefined, { limit });

export const getIngestDetail = (docId: string) => apiFetch<IngestDetail>(`/api/ingests/${docId}`);

export const searchEntities = (q: string, entityType?: string, limit = 12) =>
  apiFetch<EntityListResponse>("/api/entities", undefined, { q, entity_type: entityType, limit });

export const getGraph = (rootEntityId: string, depth = 1, limit = 50) =>
  apiFetch<GraphResponse>("/api/graph", undefined, { root_entity_id: rootEntityId, depth, limit });

export const listCouncilCases = () => apiFetch<CouncilCasesResponse>("/api/council/cases");

export const retryCouncilCase = (caseId: string) =>
  apiFetch<CouncilRetryResponse>(`/api/council/cases/${caseId}/retry`, { method: "POST" });

export const processPendingCouncilCases = () =>
  apiFetch<Record<string, number>>("/api/council/process-pending", { method: "POST" });

export const askGraph = (question: string) =>
  apiFetch<AskResponse>("/api/ask", {
    method: "POST",
    body: JSON.stringify({ question }),
  });

export const ingestText = (text: string, metadata: Record<string, unknown>) =>
  apiFetch<IngestResult>("/api/text/add-to-vectordb", {
    method: "POST",
    body: JSON.stringify({ text, metadata }),
  });

export const ingestPdf = (payload: { pdfData: string; filename: string; metadata: Record<string, unknown> }) =>
  apiFetch<IngestResult>("/api/pdf/extract-and-embed", {
    method: "POST",
    body: JSON.stringify({
      pdf_data: payload.pdfData,
      filename: payload.filename,
      metadata: payload.metadata,
    }),
  });

export const readFileAsBase64 = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("Failed to encode file"));
        return;
      }

      const [, base64] = result.split(",");
      resolve(base64 ?? "");
    };
    reader.readAsDataURL(file);
  });
