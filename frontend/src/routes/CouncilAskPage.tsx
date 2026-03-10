import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { SectionCard } from "../components/SectionCard";
import { askGraph, listCouncilCases, processPendingCouncilCases, retryCouncilCase } from "../lib/api";

export const CouncilAskPage = () => {
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
      setActionMessage(`Processed ${payload.result.processed ?? 0} pending case after retry.`);
      void queryClient.invalidateQueries({ queryKey: ["council-cases"] });
    },
    onError: () => setActionMessage("Retry failed. Please try again."),
  });

  const processMutation = useMutation({
    mutationFn: processPendingCouncilCases,
    onSuccess: (payload) => {
      setActionMessage(`Processed ${payload.processed ?? 0} pending case in the queue.`);
      void queryClient.invalidateQueries({ queryKey: ["council-cases"] });
    },
    onError: () => setActionMessage("Processing failed. Please try again."),
  });

  const askMutation = useMutation({
    mutationFn: () => askGraph(question),
    onError: () => setActionMessage("Ask graph failed. Please try again."),
  });

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="page-eyebrow">Council Operations</p>
          <h1>Council &amp; Ask</h1>
          <p>Review pending graph disputes, trigger retry automation, and run a reasoning query in one surface.</p>
        </div>
      </header>

      <div className="content-grid">
        <SectionCard
          action={
            <button className="secondary-button" onClick={() => processMutation.mutate()} type="button">
              Process pending
            </button>
          }
          title="Council Queue"
          subtitle="Cases waiting for operator attention or worker processing."
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
            <button className="primary-button" onClick={() => retryMutation.mutate()} type="button">
              Retry selected case
            </button>
          ) : null}
          {actionMessage ? <p className="inline-note">{actionMessage}</p> : null}
        </SectionCard>

        <SectionCard title="Ask the Graph" subtitle="Run a direct reasoning query against the current knowledge graph.">
          <label className="field-label" htmlFor="question">
            Question
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
            Ask graph
          </button>

          {askMutation.data ? (
            <div className="result-card">
              <p>{askMutation.data.answer}</p>
              <div className="result-row">
                <span>Confidence</span>
                <strong>{askMutation.data.confidence}</strong>
              </div>
            </div>
          ) : null}
        </SectionCard>
      </div>
    </div>
  );
};
