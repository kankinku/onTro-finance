import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useI18n } from "../app/i18n";
import { SectionCard } from "../components/SectionCard";
import { askGraph, decideCouncilCase, listCouncilCases, processPendingCouncilCases, retryCouncilCase } from "../lib/api";

export const CouncilAskPage = () => {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const casesQuery = useQuery({
    queryKey: ["council-cases"],
    queryFn: listCouncilCases,
  });

  useEffect(() => {
    if (!selectedCaseId && casesQuery.data?.cases.length) {
      setSelectedCaseId(casesQuery.data.cases[0].case_id);
    }
  }, [casesQuery.data, selectedCaseId]);

  const retryMutation = useMutation({
    mutationFn: async () => {
      if (!selectedCaseId) {
        throw new Error("No case selected");
      }

      return retryCouncilCase(selectedCaseId);
    },
    onSuccess: (payload) => {
      setActionMessage(t("council.queue.processedRetry", { count: payload.result.processed ?? 0 }));
      void queryClient.invalidateQueries({ queryKey: ["council-cases"] });
    },
    onError: () => setActionMessage(t("council.queue.retryError")),
  });

  const decisionMutation = useMutation({
    mutationFn: async (decision: string) => {
      if (!selectedCaseId) {
        throw new Error("No case selected");
      }
      return decideCouncilCase(selectedCaseId, { decision, confidence: 0.9, rationale: `Manual ${decision}` });
    },
    onSuccess: (payload) => {
      setActionMessage(`${payload.candidate.status ?? "updated"}`);
      void queryClient.invalidateQueries({ queryKey: ["council-cases"] });
    },
    onError: () => setActionMessage(t("council.queue.retryError")),
  });

  const processMutation = useMutation({
    mutationFn: processPendingCouncilCases,
    onSuccess: (payload) => {
      setActionMessage(t("council.queue.processedQueue", { count: payload.processed ?? 0 }));
      void queryClient.invalidateQueries({ queryKey: ["council-cases"] });
    },
    onError: () => setActionMessage(t("council.queue.processError")),
  });

  const askMutation = useMutation({
    mutationFn: () => askGraph(question),
    onError: () => setActionMessage(t("council.ask.error")),
  });

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="page-eyebrow">{t("council.eyebrow")}</p>
          <h1>{t("council.title")}</h1>
          <p>{t("council.description")}</p>
        </div>
      </header>

      <div className="content-grid">
        <SectionCard
          action={
            <button className="secondary-button" onClick={() => processMutation.mutate()} type="button">
              {t("council.queue.process")}
            </button>
          }
          title={t("council.queue.title")}
          subtitle={t("council.queue.subtitle")}
        >
          <div className="chip-row">
            {casesQuery.data?.cases.map((item) => (
              <button
                key={item.case_id}
                className={`entity-button${selectedCaseId === item.case_id ? " is-selected" : ""}`}
                onClick={() => setSelectedCaseId(item.case_id)}
                type="button"
              >
                {item.case_id}
              </button>
            ))}
          </div>
          {selectedCaseId ? (
            <div className="chip-row">
              <button className="primary-button" onClick={() => retryMutation.mutate()} type="button">
                {t("council.queue.retry")}
              </button>
              <button className="secondary-button" onClick={() => decisionMutation.mutate("APPROVE")} type="button">
                Approve
              </button>
              <button className="secondary-button" onClick={() => decisionMutation.mutate("REJECT")} type="button">
                Reject
              </button>
              <button className="secondary-button" onClick={() => decisionMutation.mutate("DEFER")} type="button">
                Defer
              </button>
            </div>
          ) : null}
          {actionMessage ? <p className="inline-note">{actionMessage}</p> : null}
        </SectionCard>

        <SectionCard title={t("council.ask.title")} subtitle={t("council.ask.subtitle")}>
          <label className="field-label" htmlFor="question">
            {t("common.question")}
          </label>
          <textarea
            id="question"
            className="text-input"
            rows={5}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button
            className="primary-button"
            disabled={!question.trim() || askMutation.isPending}
            onClick={() => askMutation.mutate()}
            type="button"
          >
            {t("council.ask.submit")}
          </button>

          {askMutation.data ? (
            <div className="result-card">
              <p>{askMutation.data.answer}</p>
              <div className="result-row">
                <span>{t("common.confidence")}</span>
                <strong>{askMutation.data.confidence}</strong>
              </div>
            </div>
          ) : null}
        </SectionCard>
      </div>
    </div>
  );
};
