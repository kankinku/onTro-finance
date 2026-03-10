import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { SectionCard } from "../components/SectionCard";
import { ingestPdf, ingestText, readFileAsBase64 } from "../lib/api";
import type { IngestResult } from "../lib/types";

export const DataIntakePage = () => {
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
      void queryClient.invalidateQueries({ queryKey: ["ingests"] });
    },
    onError: () => setError("Text ingest failed."),
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
      void queryClient.invalidateQueries({ queryKey: ["ingests"] });
    },
    onError: () => setError("PDF ingest failed."),
  });

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="page-eyebrow">Pipeline Input</p>
          <h1>Data Intake</h1>
          <p>Submit raw text or a PDF, then move directly into the saved record and council follow-up.</p>
        </div>
      </header>

      <div className="content-grid two-up">
        <SectionCard title="Text Intake" subtitle="Paste analysis, notes, or market commentary.">
          <label className="field-label" htmlFor="analysis-text">
            Analysis text
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
            Submit text
          </button>
        </SectionCard>

        <SectionCard title="PDF Intake" subtitle="Upload a report or internal brief for extraction.">
          <label className="field-label" htmlFor="pdf-file">
            PDF file
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
            Submit PDF
          </button>
        </SectionCard>
      </div>

      <SectionCard title="Latest Result" subtitle="Immediate ingest feedback for the operator.">
        {result ? (
          <div className="result-card">
            <div className="result-row">
              <span>Document ID</span>
              <strong>{result.doc_id}</strong>
            </div>
            <div className="result-row">
              <span>Edges extracted</span>
              <strong>{result.edge_count}</strong>
            </div>
            <div className="chip-row">
              {Object.entries(result.destinations).map(([key, value]) => (
                <span key={key} className="data-chip">
                  {key}: {value}
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
              Open saved record
            </Link>
          </div>
        ) : (
          <p className="empty-state">No ingest has been submitted in this session yet.</p>
        )}
        {error ? <p className="inline-error">{error}</p> : null}
      </SectionCard>
    </div>
  );
};
