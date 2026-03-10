import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useI18n } from "../app/i18n";
import { SectionCard } from "../components/SectionCard";
import { ingestPdf, ingestText, readFileAsBase64 } from "../lib/api";
import { queryKeys } from "../lib/queryKeys";
import type { IngestResult } from "../lib/types";

export const DataIntakePage = () => {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [result, setResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const textMutation = useMutation({
    mutationFn: async () => ingestText(text, {}),
    onSuccess: (payload) => {
      setResult(payload);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.ingests });
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents });
    },
    onError: () => setError(t("intake.text.error")),
  });

  const pdfMutation = useMutation({
    mutationFn: async () => {
      if (!pdfFile) {
        throw new Error("No PDF selected");
      }

      return ingestPdf({
        pdfData: await readFileAsBase64(pdfFile),
        filename: pdfFile.name,
        metadata: {},
      });
    },
    onSuccess: (payload) => {
      setResult(payload);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.ingests });
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents });
    },
    onError: () => setError(t("intake.pdf.error")),
  });

  const destinationLabel = (key: string) => t(`common.destinations.${key}`);

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="page-eyebrow">{t("intake.eyebrow")}</p>
          <h1>{t("intake.title")}</h1>
          <p>{t("intake.description")}</p>
        </div>
      </header>

      <div className="content-grid two-up">
        <SectionCard title={t("intake.text.title")} subtitle={t("intake.text.subtitle")}>
          <label className="field-label" htmlFor="analysis-text">
            {t("intake.text.label")}
          </label>
          <textarea
            id="analysis-text"
            className="text-input"
            rows={8}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <button
            className="primary-button"
            disabled={!text.trim() || textMutation.isPending}
            onClick={() => textMutation.mutate()}
            type="button"
          >
            {t("intake.text.submit")}
          </button>
        </SectionCard>

        <SectionCard title={t("intake.pdf.title")} subtitle={t("intake.pdf.subtitle")}>
          <label className="field-label" htmlFor="pdf-file">
            {t("intake.pdf.label")}
          </label>
          <input
            id="pdf-file"
            accept="application/pdf"
            className="file-input"
            type="file"
            onChange={(event) => setPdfFile(event.target.files?.[0] ?? null)}
          />
          <button
            className="secondary-button"
            disabled={!pdfFile || pdfMutation.isPending}
            onClick={() => pdfMutation.mutate()}
            type="button"
          >
            {t("intake.pdf.submit")}
          </button>
        </SectionCard>
      </div>

      <SectionCard title={t("intake.result.title")} subtitle={t("intake.result.subtitle")}>
        {result ? (
          <div className="result-card">
            <div className="result-row">
              <span>{t("common.documentId")}</span>
              <strong>{result.doc_id}</strong>
            </div>
            <div className="result-row">
              <span>{t("common.edgesExtracted", { count: result.edge_count })}</span>
              <strong>{result.edge_count}</strong>
            </div>
            <div className="chip-row">
              {Object.entries(result.destinations).map(([key, value]) => (
                <span key={key} className="data-chip">
                  {destinationLabel(key)}: {value}
                </span>
              ))}
            </div>
            <div className="chip-row">
              {result.council_case_ids.map((caseId) => (
                <span key={caseId} className="data-chip accent-chip">
                  {caseId}
                </span>
              ))}
            </div>
            <Link className="inline-link" to={`/saved?doc=${result.doc_id}`}>
              {t("common.openSavedRecord")}
            </Link>
          </div>
        ) : (
          <p className="empty-state">{t("intake.result.empty")}</p>
        )}
        {error ? <p className="inline-error">{error}</p> : null}
      </SectionCard>
    </div>
  );
};
