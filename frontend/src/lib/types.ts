export interface DashboardSummary {
  status: string;
  totals: {
    ingests: number;
    entities: number;
    relations: number;
  };
  council: {
    pending: number;
    closed: number;
    available_members: number;
  };
  recent_ingests: IngestListItem[];
  recent_errors: Array<Record<string, unknown>>;
}

export interface IngestListItem {
  doc_id: string;
  input_type: string;
  edge_count: number;
  created_at?: string;
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

export interface AskResponse {
  answer: string;
  confidence: number;
  reasoning_used: boolean;
  reasoning_trace?: string[];
  sources?: Array<Record<string, unknown>>;
}
