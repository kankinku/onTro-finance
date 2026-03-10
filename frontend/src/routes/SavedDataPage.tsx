import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { SectionCard } from "../components/SectionCard";
import { getIngestDetail, getIngests } from "../lib/api";

export const SavedDataPage = () => {
  const [searchParams] = useSearchParams();
  const docId = searchParams.get("doc") ?? "";

  const ingestListQuery = useQuery({
    queryKey: ["ingests"],
    queryFn: () => getIngests(),
  });

  const ingestDetailQuery = useQuery({
    queryKey: ["ingest-detail", docId],
    queryFn: () => getIngestDetail(docId),
    enabled: Boolean(docId),
  });

  const detail = ingestDetailQuery.data;

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="page-eyebrow">Stored Records</p>
          <h1>Saved Data</h1>
          <p>Inspect ingest history, open a specific record, and move out to graph or council review.</p>
        </div>
      </header>

      <div className="content-grid">
        <SectionCard title="Recent Records" subtitle="The ingest ledger is append-only and ordered by recency.">
          <ul className="data-list">
            {ingestListQuery.data?.items.length ? (
              ingestListQuery.data.items.map((item) => (
                <li key={item.doc_id}>
                  <Link className="inline-link" to={`/saved?doc=${item.doc_id}`}>
                    {item.doc_id}
                  </Link>
                  <span>{item.edge_count} edges</span>
                </li>
              ))
            ) : (
              <li className="empty-state">No saved ingest records available.</li>
            )}
          </ul>
        </SectionCard>

        <SectionCard title="Record Detail" subtitle="Operator-friendly summary for the selected document.">
          {detail ? (
            <div className="detail-stack">
              <h3>{detail.metadata.doc_title?.toString() ?? detail.doc_id}</h3>
              <p>{detail.edge_count} edges extracted</p>
              <div className="chip-row">
                {Object.entries(detail.destinations ?? {}).map(([key, value]) => (
                  <span key={key} className="data-chip">
                    {key}: {value}
                  </span>
                ))}
              </div>
              <div className="chip-row">
                {detail.council_case_ids?.map((caseId) => (
                  <span key={caseId} className="data-chip accent-chip">
                    {caseId}
                  </span>
                ))}
              </div>
              <div className="link-row">
                <Link className="inline-link" to="/graph">
                  Open graph explorer
                </Link>
                <Link className="inline-link" to="/council">
                  Open council
                </Link>
              </div>
            </div>
          ) : (
            <p className="empty-state">Select a document to view ingest detail.</p>
          )}
        </SectionCard>
      </div>
    </div>
  );
};
