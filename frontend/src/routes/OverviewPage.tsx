import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { SectionCard } from "../components/SectionCard";
import { StatCard } from "../components/StatCard";
import { StatusPill } from "../components/StatusPill";
import { useI18n } from "../app/i18n";
import { getAuditLogs, getDashboardSummary, promoteLearningBundle, runLearningEvaluation } from "../lib/api";
import type { LearningProductItem } from "../lib/types";

export const OverviewPage = () => {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [goldsetFilename, setGoldsetFilename] = useState("gold-test.json");
  const [snapshotFilename, setSnapshotFilename] = useState("dataset-test.json");
  const [bundleFilename, setBundleFilename] = useState("bundle-test.json");
  const [auditAction, setAuditAction] = useState("");
  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: getDashboardSummary,
  });
  const auditQuery = useQuery({
    queryKey: ["audit-logs", auditAction],
    queryFn: () => getAuditLogs(10, auditAction || undefined),
  });

  const summary = summaryQuery.data;
  const statusLabel = t(`common.status.${summary?.status ?? "loading"}`);
  const trustEntries = Object.entries(summary?.trust?.trigger_reason_counts ?? {}).slice(0, 3);
  const learningItems = (summary?.learning?.items ?? []).slice(0, 4) as LearningProductItem[];
  const auditItems = auditQuery.data?.items ?? summary?.audit?.items ?? [];

  const evaluationMutation = useMutation({
    mutationFn: () => runLearningEvaluation({ goldsetFilename, snapshotFilename }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] }),
  });

  const promoteMutation = useMutation({
    mutationFn: () => promoteLearningBundle({ bundleFilename, approved: true, deploy: true, notes: "Promoted from console" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] }),
  });

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="page-eyebrow">{t("overview.eyebrow")}</p>
          <h1>{t("overview.title")}</h1>
          <p>{t("overview.description")}</p>
        </div>
        <StatusPill
          label={statusLabel}
          tone={summary?.status === "ready" ? "success" : "warning"}
        />
      </header>

      <section className="stat-grid">
        <StatCard label={t("overview.stats.ingests")} tone="accent" value={summary?.totals.ingests ?? "-"} />
        <StatCard label={t("overview.stats.entities")} value={summary?.totals.entities ?? "-"} />
        <StatCard label={t("overview.stats.relations")} tone="warm" value={summary?.totals.relations ?? "-"} />
        <StatCard label={t("overview.stats.councilPending")} value={summary?.council.pending ?? "-"} />
      </section>

      <div className="content-grid">
        <SectionCard title={t("overview.recent.title")} subtitle={t("overview.recent.subtitle")}>
          <ul className="data-list">
            {summary?.recent_ingests.length ? (
              summary.recent_ingests.map((item) => (
                <li key={item.doc_id}>
                  <strong>{item.metadata.doc_title?.toString() ?? item.doc_id}</strong>
                  <span>{t("common.edgesExtracted", { count: item.edge_count })}</span>
                </li>
              ))
            ) : (
              <li className="empty-state">{t("overview.recent.empty")}</li>
            )}
          </ul>
        </SectionCard>

        <SectionCard title={t("overview.council.title")} subtitle={t("overview.council.subtitle")}>
          <dl className="metric-list">
            <div>
              <dt>{t("overview.council.pending")}</dt>
              <dd>{summary?.council.pending ?? "-"}</dd>
            </div>
            <div>
              <dt>{t("overview.council.closed")}</dt>
              <dd>{summary?.council.closed ?? "-"}</dd>
            </div>
            <div>
              <dt>{t("overview.council.available")}</dt>
              <dd>{summary?.council.available_members ?? "-"}</dd>
            </div>
          </dl>
        </SectionCard>
      </div>

      <div className="content-grid">
        <SectionCard title={t("overview.trust.title")} subtitle={t("overview.trust.subtitle")}>
          {summary?.trust ? (
            <div className="detail-stack">
              <dl className="metric-list compact-metric-list">
                <div>
                  <dt>{t("overview.trust.confidence")}</dt>
                  <dd>
                    {Object.entries(summary.trust.confidence_bands)
                      .map(([label, count]) => `${label}:${count}`)
                      .join(" / ")}
                  </dd>
                </div>
                <div>
                  <dt>{t("overview.trust.destinations")}</dt>
                  <dd>
                    {Object.entries(summary.trust.validation_destination_counts)
                      .map(([label, count]) => `${label}:${count}`)
                      .join(" / ")}
                  </dd>
                </div>
              </dl>
              <ul className="data-list">
                {trustEntries.length ? (
                  trustEntries.map(([trigger, count]) => (
                    <li key={trigger}>
                      <strong>{trigger}</strong>
                      <span>{count}</span>
                    </li>
                  ))
                ) : (
                  <li className="empty-state">{t("overview.trust.empty")}</li>
                )}
              </ul>
            </div>
          ) : (
            <p className="empty-state">{t("overview.trust.empty")}</p>
          )}
        </SectionCard>

        <SectionCard title={t("overview.learning.title")} subtitle={t("overview.learning.subtitle")}>
          <div className="search-row compact-search-row">
            <input className="inline-input" value={goldsetFilename} onChange={(event) => setGoldsetFilename(event.target.value)} placeholder="goldset filename" />
            <input className="inline-input" value={snapshotFilename} onChange={(event) => setSnapshotFilename(event.target.value)} placeholder="snapshot filename" />
          </div>
          <div className="search-row compact-search-row">
            <input className="inline-input" value={bundleFilename} onChange={(event) => setBundleFilename(event.target.value)} placeholder="bundle filename" />
          </div>
          <div className="chip-row">
            <button className="secondary-button" onClick={() => evaluationMutation.mutate()} type="button">
              Run evaluation
            </button>
            <button className="secondary-button" onClick={() => promoteMutation.mutate()} type="button">
              Promote bundle
            </button>
          </div>
          <dl className="metric-list compact-metric-list">
            <div>
              <dt>{t("overview.learning.snapshots")}</dt>
              <dd>{summary?.learning?.counts.snapshots ?? 0}</dd>
            </div>
            <div>
              <dt>{t("overview.learning.evaluations")}</dt>
              <dd>{summary?.learning?.counts.evaluations ?? 0}</dd>
            </div>
            <div>
              <dt>{t("overview.learning.bundles")}</dt>
              <dd>{summary?.learning?.counts.bundles ?? 0}</dd>
            </div>
            <div>
              <dt>{t("overview.learning.goldsets")}</dt>
              <dd>{summary?.learning?.counts.goldsets ?? 0}</dd>
            </div>
          </dl>
          <ul className="data-list">
            {learningItems.length ? (
              learningItems.map((item) => (
                <li key={`${item.kind}-${item.file_name}`}>
                  <div className="list-primary">
                    <strong>{item.version ?? item.file_name}</strong>
                    <span className="list-secondary">{item.kind}</span>
                  </div>
                  <span>{item.task_type ?? item.status ?? "-"}</span>
                </li>
              ))
            ) : (
              <li className="empty-state">-</li>
            )}
          </ul>
        </SectionCard>
      </div>

      <div className="content-grid">
        <SectionCard title={t("overview.audit.title")} subtitle={t("overview.audit.subtitle")}>
          <div className="search-row compact-search-row">
            <input className="inline-input" value={auditAction} onChange={(event) => setAuditAction(event.target.value)} placeholder="Filter action" />
          </div>
          <ul className="data-list">
            {auditItems.length ? (
              auditItems.map((item, index) => (
                <li key={`${item.path}-${item.logged_at ?? index}`}>
                  <div className="list-primary">
                    <strong>{item.action.toUpperCase()}</strong>
                    <span className="list-secondary">{item.path}</span>
                  </div>
                  <span>{item.client}</span>
                </li>
              ))
            ) : (
              <li className="empty-state">{t("overview.audit.empty")}</li>
            )}
          </ul>
        </SectionCard>
      </div>

      {summaryQuery.isError ? <p className="inline-error">{t("overview.error")}</p> : null}
    </div>
  );
};
