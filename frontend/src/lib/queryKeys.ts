export const queryKeys = {
  dashboardSummary: ["dashboard-summary"] as const,
  ingests: ["ingests"] as const,
  ingestDetail: (docId: string) => ["ingest-detail", docId] as const,
  entities: (searchTerm: string) => ["entities", searchTerm] as const,
  graph: (entityId: string, depth: number) => ["graph", entityId, depth] as const,
  councilCases: ["council-cases"] as const,
};
