export interface DashboardSummary {
  status: string;
  ready: boolean;
  totals: {
    ingests: number;
    documents?: number;
    entities: number;
    relations: number;
    edges: number;
    domain_relations: number;
    personal_relations: number;
    council_pending: number;
    council_closed: number;
  };
  council: {
    pending: number;
    closed: number;
    available_members: number;
  };
  trust?: TrustSummary;
  learning?: LearningProductsResponse;
  audit?: AuditLogResponse;
  system: {
    storage_backend: string;
    storage_ok: boolean;
    llm_available: boolean;
    council_worker_active: boolean;
    last_council_run: string | null;
    council_last_error: string | null;
  };
  recent_ingests: IngestListItem[];
  recent_documents?: DocumentListItem[];
  event_backlog: Record<string, number>;
}

export interface DocumentRelationSummary {
  head_entity_id: string;
  relation_type: string;
  tail_entity_id: string;
  destinations: string[];
  evidence_count: number;
  max_confidence: number;
  time_scopes: string[];
  semantic_tags: string[];
  council_case_ids: string[];
}

export interface DocumentEvidenceEvent {
  event_type?: string;
  edge_id?: string;
  fragment_id?: string;
  fragment_text?: string | null;
  relation_type?: string;
  destination?: string;
  combined_conf?: number;
  confidence?: number;
  time_scope?: string | null;
  logged_at?: string | null;
  citation_text?: string | null;
}

export interface DocumentListItem {
  doc_id: string;
  title?: string | null;
  author?: string | null;
  institution?: string | null;
  source_type?: string | null;
  published_at?: string | null;
  language?: string | null;
  region?: string | null;
  asset_scope?: string | null;
  document_quality_tier?: string | null;
  input_type?: string | null;
  edge_count: number;
  destinations?: Record<string, number>;
  metadata: Record<string, unknown>;
  updated_at?: string | null;
}

export interface DocumentListResponse {
  items: DocumentListItem[];
}

export interface TrustSummary {
  candidate_status_counts: Record<string, number>;
  trigger_reason_counts: Record<string, number>;
  validation_destination_counts: Record<string, number>;
  confidence_bands: Record<string, number>;
}

export interface LearningProductItem {
  kind: string;
  file_name: string;
  version?: string | null;
  task_type?: string | null;
  sample_count?: number | null;
  dataset_id?: string | null;
  dataset_version?: string | null;
  goldset_version?: string | null;
  f1?: number | null;
  accuracy?: number | null;
  goldset_id?: string | null;
  status?: string | null;
  student1_version?: string | null;
  student2_version?: string | null;
  policy_version?: string | null;
  deployed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface LearningProductsResponse {
  counts: {
    snapshots: number;
    evaluations: number;
    bundles: number;
    goldsets: number;
  };
  items: LearningProductItem[];
}

export interface LearningProductDetailResponse {
  kind: string;
  file_name: string;
  path: string;
  payload: Record<string, unknown>;
}

export interface LearningEvaluationRunResponse {
  snapshot_filename: string;
  goldset_filename: string;
  evaluation_filename: string;
  metrics: Record<string, number>;
}

export interface AuditLogItem {
  event_id?: string;
  action: string;
  path: string;
  client: string;
  logged_at?: string;
}

export interface AuditLogResponse {
  items: AuditLogItem[];
  count: number;
}

export interface AuditLogDetailResponse extends AuditLogItem {
  event_id?: string;
  event_type?: string;
  role?: string | null;
  [key: string]: unknown;
}

export interface DocumentDetail extends DocumentListItem {
  filename?: string | null;
  text_preview?: string | null;
  council_case_ids?: string[];
  created_at?: string | null;
  consolidated_relations?: Array<Record<string, unknown>>;
  related_relations: DocumentRelationSummary[];
  evidence: {
    validation_events: DocumentEvidenceEvent[];
    council_events: DocumentEvidenceEvent[];
    counts: {
      validation: number;
      council: number;
      unique_relations: number;
    };
  };
}

export interface DocumentStructureResponse {
  doc_id: string;
  structured_sections: Array<Record<string, unknown>>;
  pdf_blocks: Array<Record<string, unknown>>;
  ocr_needed_pages: number[];
  table_blocks: Array<Record<string, unknown>>;
  consolidated_relations: Array<Record<string, unknown>>;
}

export interface IngestListItem {
  doc_id: string;
  input_type: string;
  edge_count: number;
  logged_at?: string;
  filename?: string | null;
  text_preview?: string | null;
  metadata: Record<string, unknown>;
  destinations?: Record<string, number>;
  council_case_ids?: string[];
}

export interface IngestListResponse {
  items: IngestListItem[];
}

export interface IngestDetail extends IngestListItem {
  filename?: string | null;
  text_preview?: string | null;
}

export interface IngestResult {
  doc_id: string;
  edge_count: number;
  destinations: Record<string, number>;
  council_case_ids: string[];
}

export interface DeleteIngestsResponse {
  status: string;
  deleted_doc_ids: string[];
  remaining_ingests: number;
}

export interface AiRuntimeStatus {
  provider: string;
  provider_label: string;
  model_name: string;
  base_url: string;
  auth_type: string;
  auth_required: boolean;
  auth_configured: boolean;
  connected: boolean;
  status: string;
  message: string;
  checked_url?: string | null;
  available_models: string[];
  missing_env: string[];
  last_checked_at?: string | null;
  attempts: number;
  members?: AiRuntimeMemberStatus[];
}

export interface AiRuntimeMemberStatus {
  member_id: string;
  role: string;
  provider: string;
  provider_label: string;
  model_name: string;
  base_url: string;
  auth_type: string;
  auth_required: boolean;
  auth_configured: boolean;
  connected: boolean;
  status: string;
  message: string;
  checked_url?: string | null;
  available_models: string[];
  missing_env: string[];
  attempts: number;
}

export interface EntitySummary {
  id: string;
  label: string;
  kind: string;
  meta: Record<string, unknown>;
}

export interface EntityListResponse {
  items: EntitySummary[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  sign?: string | null;
  confidence?: number | null;
  origin?: string | null;
  meta?: Record<string, unknown>;
}

export interface GraphResponse {
  nodes: EntitySummary[];
  edges: GraphEdge[];
}

export interface CouncilCase {
  case_id: string;
  status: string;
  candidate_id?: string | null;
  [key: string]: unknown;
}

export interface CouncilCasesResponse {
  cases: CouncilCase[];
}

export interface CouncilRetryResponse {
  case: CouncilCase;
  result: Record<string, number>;
}

export interface CouncilDecisionResponse {
  case: CouncilCase | null;
  candidate: Record<string, unknown>;
}

export interface AskResponse {
  answer: string;
  confidence: number;
  reasoning_used: boolean;
  reasoning_trace?: string[];
  sources?: Array<Record<string, unknown>>;
}
