import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useI18n } from "../app/i18n";
import { SectionCard } from "../components/SectionCard";
import { getDocumentDetail, getDocumentGraph, getDocumentStructure, getDocuments, getIngestDetail, getIngests } from "../lib/api";
import { queryKeys } from "../lib/queryKeys";

export const SavedDataPage = () => {
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const docId = searchParams.get("doc") ?? "";
  const [searchTerm, setSearchTerm] = useState("");
  const [sourceTypeFilter, setSourceTypeFilter] = useState("");

  const ingestListQuery = useQuery({
    queryKey: queryKeys.ingests,
    queryFn: () => getIngests(),
  });

  const documentListQuery = useQuery({
    queryKey: [...queryKeys.documents, searchTerm, sourceTypeFilter],
    queryFn: () => getDocuments({ q: searchTerm, sourceType: sourceTypeFilter || undefined }),
  });

  const ingestDetailQuery = useQuery({
    queryKey: queryKeys.ingestDetail(docId),
    queryFn: () => getIngestDetail(docId),
    enabled: Boolean(docId),
  });

  const documentDetailQuery = useQuery({
    queryKey: queryKeys.documentDetail(docId),
    queryFn: () => getDocumentDetail(docId),
    enabled: Boolean(docId),
  });

  const documentGraphQuery = useQuery({
    queryKey: queryKeys.documentGraph(docId),
    queryFn: () => getDocumentGraph(docId),
    enabled: Boolean(docId),
  });

  const documentStructureQuery = useQuery({
    queryKey: queryKeys.documentStructure(docId),
    queryFn: () => getDocumentStructure(docId),
    enabled: Boolean(docId),
  });

  const detail = ingestDetailQuery.data;
  const documentDetail = documentDetailQuery.data;
  const documentGraph = documentGraphQuery.data;
  const documentStructure = documentStructureQuery.data;
  const graphNodes = documentGraph?.nodes ?? [];
  const graphEdges = documentGraph?.edges ?? [];
  const structuredSections = documentStructure?.structured_sections ?? [];
  const tableBlocks = documentStructure?.table_blocks ?? [];
  const ocrPages = documentStructure?.ocr_needed_pages ?? [];
  const destinationLabel = (key: string) => t(`common.destinations.${key}`);

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="page-eyebrow">{t("saved.eyebrow")}</p>
          <h1>{t("saved.title")}</h1>
          <p>{t("saved.description")}</p>
        </div>
      </header>

      <div className="content-grid">
        <SectionCard title={t("saved.recent.title")} subtitle={t("saved.recent.subtitle")}>
          <div className="search-row compact-search-row">
            <input
              aria-label={t("saved.document.filters.search")}
              className="inline-input"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder={t("saved.document.filters.search")}
            />
            <select
              aria-label={t("saved.document.filters.sourceType")}
              className="inline-input select-input"
              value={sourceTypeFilter}
              onChange={(event) => setSourceTypeFilter(event.target.value)}
            >
              <option value="">{t("saved.document.filters.allSources")}</option>
              <option value="research_note">research_note</option>
              <option value="internal_memo">internal_memo</option>
              <option value="policy_note">policy_note</option>
            </select>
          </div>
          <ul className="data-list">
            {documentListQuery.data?.items.length ? (
              documentListQuery.data.items.map((item) => (
                <li key={item.doc_id}>
                  <div className="list-primary">
                    <Link className="inline-link" to={`/saved?doc=${item.doc_id}`}>
                      {item.title ?? item.doc_id}
                    </Link>
                    <span className="list-secondary">{item.doc_id}</span>
                  </div>
                  <span>{t("common.edgesExtracted", { count: item.edge_count })}</span>
                </li>
              ))
            ) : (
              <li className="empty-state">{t("saved.recent.empty")}</li>
            )}
          </ul>
        </SectionCard>

        <SectionCard title={t("saved.detail.title")} subtitle={t("saved.detail.subtitle")}>
          {detail && documentDetail ? (
            <div className="detail-stack">
              <div>
                <h3>{documentDetail.title ?? detail.metadata.doc_title?.toString() ?? detail.doc_id}</h3>
                <p>{t("common.edgesExtracted", { count: documentDetail.edge_count })}</p>
              </div>
              <dl className="metric-list compact-metric-list">
                <div>
                  <dt>{t("common.documentId")}</dt>
                  <dd>{documentDetail.doc_id}</dd>
                </div>
                <div>
                  <dt>{t("saved.document.sourceType")}</dt>
                  <dd>{documentDetail.source_type ?? "-"}</dd>
                </div>
                <div>
                  <dt>{t("saved.document.institution")}</dt>
                  <dd>{documentDetail.institution ?? "-"}</dd>
                </div>
                <div>
                  <dt>{t("saved.document.author")}</dt>
                  <dd>{documentDetail.author ?? "-"}</dd>
                </div>
              </dl>
              <div className="chip-row">
                {Object.entries(documentDetail.destinations ?? {}).map(([key, value]) => (
                  <span key={key} className="data-chip">
                    {destinationLabel(key)}: {value}
                  </span>
                ))}
              </div>
              <div className="chip-row">
                {documentDetail.council_case_ids?.map((caseId) => (
                  <span key={caseId} className="data-chip accent-chip">
                    {caseId}
                  </span>
                ))}
              </div>
              <SectionCard
                title={t("saved.document.relations.title")}
                subtitle={t("saved.document.relations.subtitle", {
                  count: documentDetail.evidence.counts.unique_relations,
                })}
              >
                <ul className="data-list">
                  {documentDetail.related_relations.length ? (
                    documentDetail.related_relations.map((relation) => (
                      <li key={`${relation.head_entity_id}-${relation.relation_type}-${relation.tail_entity_id}`}>
                        <div className="list-primary">
                          <strong>
                            {relation.head_entity_id} - {relation.relation_type} - {relation.tail_entity_id}
                          </strong>
                          <span className="list-secondary">
                            {t("saved.document.relations.evidenceCount", {
                              count: relation.evidence_count,
                            })}
                          </span>
                        </div>
                        <div className="chip-row compact-chip-row">
                          {relation.destinations.map((destination) => (
                            <span key={destination} className="data-chip">
                              {destinationLabel(destination)}
                            </span>
                          ))}
                          {relation.time_scopes.map((scope) => (
                            <span key={scope} className="data-chip neutral-chip">
                              {scope}
                            </span>
                          ))}
                        </div>
                      </li>
                    ))
                  ) : (
                    <li className="empty-state">{t("saved.document.relations.empty")}</li>
                  )}
                </ul>
              </SectionCard>
              <SectionCard
                title={t("saved.document.evidence.title")}
                subtitle={t("saved.document.evidence.subtitle", {
                  validation: documentDetail.evidence.counts.validation,
                  council: documentDetail.evidence.counts.council,
                })}
              >
                <ul className="data-list">
                  {documentDetail.evidence.validation_events.length ||
                  documentDetail.evidence.council_events.length ? (
                    [...documentDetail.evidence.validation_events, ...documentDetail.evidence.council_events]
                      .slice(0, 6)
                      .map((event, index) => (
                        <li key={`${event.event_type ?? event.edge_id ?? "event"}-${index}`}>
                          <div className="list-primary">
                            <strong>{event.relation_type ?? t("saved.document.evidence.unknown")}</strong>
                            <span className="list-secondary">
                              {event.fragment_text ?? event.citation_text ?? t("saved.document.evidence.noExcerpt")}
                            </span>
                          </div>
                          <div className="chip-row compact-chip-row">
                            <span className="data-chip neutral-chip">
                              {event.event_type ?? event.destination ?? t("saved.document.evidence.validation")}
                            </span>
                            {event.time_scope ? (
                              <span className="data-chip neutral-chip">{event.time_scope}</span>
                            ) : null}
                          </div>
                        </li>
                      ))
                  ) : (
                    <li className="empty-state">{t("saved.document.evidence.empty")}</li>
                  )}
                </ul>
              </SectionCard>
              <SectionCard title="Document Structure" subtitle="Pages, OCR flags, and detected table blocks.">
                <dl className="metric-list compact-metric-list">
                  <div>
                    <dt>Sections</dt>
                    <dd>{structuredSections.length}</dd>
                  </div>
                  <div>
                    <dt>Table blocks</dt>
                    <dd>{tableBlocks.length}</dd>
                  </div>
                  <div>
                    <dt>OCR pages</dt>
                    <dd>{ocrPages.join(", ") || "-"}</dd>
                  </div>
                </dl>
                {tableBlocks.length ? <p>{String(tableBlocks[0].caption ?? "")}</p> : null}
              </SectionCard>
              <SectionCard title="Document Subgraph" subtitle="Entities and edges tied to this document.">
                <dl className="metric-list compact-metric-list">
                  <div>
                    <dt>Nodes</dt>
                    <dd>{graphNodes.length}</dd>
                  </div>
                  <div>
                    <dt>Edges</dt>
                    <dd>{graphEdges.length}</dd>
                  </div>
                </dl>
              </SectionCard>
              <div className="link-row">
                <Link className="inline-link" to="/graph">
                  {t("common.openGraphExplorer")}
                </Link>
                <Link className="inline-link" to="/council">
                  {t("common.openCouncil")}
                </Link>
              </div>
            </div>
          ) : (
            <p className="empty-state">{t("saved.detail.empty")}</p>
          )}
        </SectionCard>
      </div>
    </div>
  );
};
