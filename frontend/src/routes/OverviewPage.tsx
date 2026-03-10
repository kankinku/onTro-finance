import { useQuery } from "@tanstack/react-query";

import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { SectionCard } from "../components/SectionCard";
import { StatCard } from "../components/StatCard";
import { StatusPill } from "../components/StatusPill";
import { getDashboardSummary } from "../lib/api";
import { queryKeys } from "../lib/queryKeys";

export const OverviewPage = () => {
  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: getDashboardSummary,
  });

  const summary = summaryQuery.data;

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="page-eyebrow">Control Surface</p>
          <h1>Overview</h1>
          <p>Monitor intake volume, relation coverage, and council pressure from one place.</p>
        </div>
        <StatusPill
          label={summary?.status ?? "loading"}
          tone={summary?.status === "ready" ? "success" : "warning"}
        />
      </header>

      <section className="stat-grid">
        <StatCard label="Documents ingested" tone="accent" value={summary?.totals.ingests ?? "-"} />
        <StatCard label="Entities tracked" value={summary?.totals.entities ?? "-"} />
        <StatCard label="Relations tracked" tone="warm" value={summary?.totals.relations ?? "-"} />
        <StatCard label="Council pending" value={summary?.council.pending ?? "-"} />
      </section>

      <div className="content-grid">
        <SectionCard title="Recent Intake" subtitle="The latest items ready for inspection or follow-up.">
          <ul className="data-list">
            {summary?.recent_ingests.length ? (
              summary.recent_ingests.map((item) => (
                <li key={item.doc_id}>
                  <strong>{item.metadata.doc_title?.toString() ?? item.doc_id}</strong>
                  <span>{item.edge_count} edges extracted</span>
                </li>
              ))
            ) : (
              <li className="empty-state">No recent ingest records yet.</li>
            )}
          </ul>
        </SectionCard>

        <SectionCard title="Council Readiness" subtitle="Pending reviews, closed work, and active members.">
          <dl className="metric-list">
            <div>
              <dt>Pending cases</dt>
              <dd>{summary?.council.pending ?? "-"}</dd>
            </div>
            <div>
              <dt>Closed cases</dt>
              <dd>{summary?.council.closed ?? "-"}</dd>
            </div>
            <div>
              <dt>Available members</dt>
              <dd>{summary?.council.available_members ?? "-"}</dd>
            </div>
          </dl>
        </SectionCard>
      </div>

      {summaryQuery.isError ? <p className="inline-error">Dashboard data could not be loaded.</p> : null}
    </div>
  );
};
