import type {
  AskResponse,
  AiRuntimeStatus,
  AuditLogResponse,
  CouncilCasesResponse,
  CouncilDecisionResponse,
  CouncilRetryResponse,
  DeleteIngestsResponse,
  DashboardSummary,
  DocumentDetail,
  DocumentListResponse,
  DocumentStructureResponse,
  EntityListResponse,
  GraphResponse,
  IngestDetail,
  IngestListResponse,
  IngestResult,
  LearningEvaluationRunResponse,
  LearningProductsResponse,
  TrustSummary,
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
    let message = "";
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
      message = payload?.detail ?? "";
    }
    if (!message) {
      message = await response.text();
    }
    throw new ApiError(message || "Request failed", response.status);
  }

  return (await response.json()) as T;
};

export const getDashboardSummary = () => apiFetch<DashboardSummary>("/api/dashboard/summary");

export const getAuditLogs = (limit = 20, action?: string) =>
  apiFetch<AuditLogResponse>("/api/audit/logs", undefined, { limit, action });

export const getIngests = (limit = 20) =>
  apiFetch<IngestListResponse>("/api/ingests", undefined, { limit });

export const getIngestDetail = (docId: string) => apiFetch<IngestDetail>(`/api/ingests/${docId}`);

export const getDocuments = (
  params: {
    limit?: number;
    q?: string;
    sourceType?: string;
    institution?: string;
    region?: string;
    assetScope?: string;
    documentQualityTier?: string;
  } = {},
) =>
  apiFetch<DocumentListResponse>("/api/documents", undefined, {
    limit: params.limit ?? 20,
    q: params.q,
    source_type: params.sourceType,
    institution: params.institution,
    region: params.region,
    asset_scope: params.assetScope,
    document_quality_tier: params.documentQualityTier,
  });

export const getDocumentDetail = (docId: string) => apiFetch<DocumentDetail>(`/api/documents/${docId}`);

export const getDocumentGraph = (docId: string) => apiFetch<GraphResponse>(`/api/documents/${docId}/graph`);

export const getDocumentStructure = (docId: string) =>
  apiFetch<DocumentStructureResponse>(`/api/documents/${docId}/structure`);

export const getTrustSummary = () => apiFetch<TrustSummary>("/api/trust/summary");

export const getLearningProducts = (limit = 10) =>
  apiFetch<LearningProductsResponse>("/api/learning/products", undefined, { limit });

export const runLearningEvaluation = (payload: { snapshotFilename?: string; goldsetFilename: string; taskType?: string }) =>
  apiFetch<LearningEvaluationRunResponse>("/api/learning/evaluations/run", {
    method: "POST",
    body: JSON.stringify({
      snapshot_filename: payload.snapshotFilename,
      goldset_filename: payload.goldsetFilename,
      task_type: payload.taskType,
    }),
  });

export const promoteLearningBundle = (payload: { bundleFilename: string; approved?: boolean; deploy?: boolean; notes?: string }) =>
  apiFetch<Record<string, unknown>>("/api/learning/bundles/promote", {
    method: "POST",
    body: JSON.stringify({
      bundle_filename: payload.bundleFilename,
      approved: payload.approved ?? true,
      deploy: payload.deploy ?? false,
      notes: payload.notes ?? "",
    }),
  });

export const deleteIngests = (docIds: string[]) =>
  apiFetch<DeleteIngestsResponse>("/api/ingests/delete", {
    method: "POST",
    body: JSON.stringify({ doc_ids: docIds }),
  });

export const getAiRuntimeStatus = () => apiFetch<AiRuntimeStatus>("/api/system/ai-runtime");

export const checkAiRuntimeStatus = () =>
  apiFetch<AiRuntimeStatus>("/api/system/ai-runtime/check", { method: "POST" });

export const searchEntities = (q: string, entityType?: string, limit = 12) =>
  apiFetch<EntityListResponse>("/api/entities", undefined, { q, entity_type: entityType, limit });

export const getGraph = (rootEntityId: string, depth = 1, limit = 50) =>
  apiFetch<GraphResponse>("/api/graph", undefined, { root_entity_id: rootEntityId, depth, limit });

export const listCouncilCases = () => apiFetch<CouncilCasesResponse>("/api/council/cases");

export const retryCouncilCase = (caseId: string) =>
  apiFetch<CouncilRetryResponse>(`/api/council/cases/${caseId}/retry`, { method: "POST" });

export const decideCouncilCase = (caseId: string, payload: { decision: string; confidence?: number; rationale?: string }) =>
  apiFetch<CouncilDecisionResponse>(`/api/council/cases/${caseId}/decision`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

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
