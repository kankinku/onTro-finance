import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useI18n } from "../app/i18n";
import { checkAiRuntimeStatus, deleteIngests, getAiRuntimeStatus, getIngests } from "../lib/api";
import { queryKeys } from "../lib/queryKeys";
import type { AiRuntimeStatus } from "../lib/types";

interface SettingsDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

const getErrorMessage = (error: unknown, fallback: string) => {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
};

const getAiRuntimeMessage = (
  locale: "en" | "ko",
  aiRuntime: Pick<AiRuntimeStatus, "provider" | "message" | "base_url">,
) => {
  if (aiRuntime.provider === "ollama" && aiRuntime.message.includes("WinError 10061")) {
    return locale === "ko"
      ? "Ollama 서버가 실행 중이지 않거나 localhost:11434 연결이 닫혀 있습니다. Ollama 앱 또는 `ollama serve`를 먼저 실행하세요."
      : "Ollama is not running or localhost:11434 is closed. Start the Ollama app or run `ollama serve` first.";
  }

  return aiRuntime.message;
};

export const SettingsDialog = ({ isOpen, onClose }: SettingsDialogProps) => {
  const { locale, setLocale, t } = useI18n();
  const queryClient = useQueryClient();
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<string | null>(null);

  const ingestQuery = useQuery({
    queryKey: [...queryKeys.ingests, "settings"],
    queryFn: () => getIngests(100),
    enabled: isOpen,
  });
  const aiRuntimeQuery = useQuery({
    queryKey: queryKeys.aiRuntime,
    queryFn: getAiRuntimeStatus,
    enabled: isOpen,
  });

  useEffect(() => {
    if (!isOpen) {
      setSelectedDocIds([]);
      setFeedback(null);
      return;
    }

    setSelectedDocIds((current) =>
      current.filter((docId) => ingestQuery.data?.items.some((item) => item.doc_id === docId) ?? true),
    );
  }, [ingestQuery.data, isOpen]);

  const deleteMutation = useMutation({
    mutationFn: (docIds: string[]) => deleteIngests(docIds),
    onSuccess: async (payload) => {
      setFeedback(t("settings.data.deleteSuccess", { count: payload.deleted_doc_ids.length }));
      setSelectedDocIds([]);
      await queryClient.invalidateQueries();
    },
    onError: (error) => {
      setFeedback(getErrorMessage(error, t("settings.data.deleteError")));
    },
  });
  const refreshAiMutation = useMutation({
    mutationFn: checkAiRuntimeStatus,
    onSuccess: (payload) => {
      queryClient.setQueryData(queryKeys.aiRuntime, payload);
    },
  });

  if (!isOpen) {
    return null;
  }

  const items = ingestQuery.data?.items ?? [];
  const aiRuntime = aiRuntimeQuery.data;
  const memberStatuses = aiRuntime?.members ?? [];
  const selectionCount = selectedDocIds.length;
  const aiStatusTone = aiRuntime?.connected ? "tone-success" : "tone-warning";
  const authTone = aiRuntime?.auth_required ? (aiRuntime.auth_configured ? "tone-success" : "tone-warning") : "tone-success";
  const authLabel = aiRuntime?.auth_required
    ? t("settings.ai.fields.authConfigured")
    : locale === "ko"
      ? "인증 필요 여부"
      : "Authentication";
  const authValue = aiRuntime?.auth_required
    ? t(`settings.ai.boolean.${aiRuntime.auth_configured ? "yes" : "no"}`)
    : locale === "ko"
      ? "필요 없음"
      : "Not required";
  const aiMessage = aiRuntime ? getAiRuntimeMessage(locale, aiRuntime) : "";

  const toggleDocId = (docId: string) => {
    setFeedback(null);
    setSelectedDocIds((current) =>
      current.includes(docId) ? current.filter((value) => value !== docId) : [...current, docId],
    );
  };

  const handleDelete = () => {
    if (!selectionCount || deleteMutation.isPending) {
      return;
    }
    deleteMutation.mutate(selectedDocIds);
  };

  return (
    <div
      aria-labelledby="settings-title"
      aria-modal="true"
      className="modal-overlay"
      onClick={onClose}
      role="dialog"
    >
      <section className="modal-card settings-dialog" onClick={(event) => event.stopPropagation()}>
        <header className="modal-header">
          <div>
            <p className="page-eyebrow">{t("settings.eyebrow")}</p>
            <h2 id="settings-title">{t("settings.title")}</h2>
          </div>
          <button aria-label={t("settings.close")} className="icon-button" onClick={onClose} type="button">
            x
          </button>
        </header>

        <div className="settings-section">
          <div className="section-header">
            <div>
              <h3>{t("settings.ai.title")}</h3>
              <p>{t("settings.ai.subtitle")}</p>
            </div>
            <button className="secondary-button" onClick={() => refreshAiMutation.mutate()} type="button">
              {refreshAiMutation.isPending ? t("settings.ai.checking") : t("settings.ai.check")}
            </button>
          </div>

          {aiRuntimeQuery.isLoading ? <p className="empty-state">{t("settings.ai.loading")}</p> : null}
          {aiRuntimeQuery.isError ? <p className="inline-error">{t("settings.ai.loadError")}</p> : null}

          {aiRuntime ? (
            <div className="settings-ai-stack">
              <section className={`settings-ai-card${aiRuntime.connected ? " is-connected" : " is-disconnected"}`}>
                <div className="settings-ai-head">
                  <div>
                    <p className="page-eyebrow">{aiRuntime.provider_label}</p>
                    <h3>{aiRuntime.model_name}</h3>
                  </div>
                  <span className={`status-pill ${aiStatusTone}`}>
                    {t(`settings.ai.connection.${aiRuntime.connected ? "connected" : "disconnected"}`)}
                  </span>
                </div>
                <div className="settings-ai-grid">
                  <div>
                    <span>{t("settings.ai.fields.provider")}</span>
                    <strong>{aiRuntime.provider_label}</strong>
                  </div>
                  <div>
                    <span>{t("settings.ai.fields.auth")}</span>
                    <strong>{t(`settings.ai.authType.${aiRuntime.auth_type}`)}</strong>
                  </div>
                  <div>
                    <span>{t("settings.ai.fields.endpoint")}</span>
                    <strong>{aiRuntime.base_url}</strong>
                  </div>
                  <div>
                    <span>{t("settings.ai.fields.attempts")}</span>
                    <strong>{aiRuntime.attempts}</strong>
                  </div>
                </div>
              </section>

              <div className="settings-ai-grid settings-ai-grid-secondary">
                <section className="settings-ai-card">
                  <div className="settings-ai-meta">
                    <span>{authLabel}</span>
                    <span className={`status-pill ${authTone}`}>{authValue}</span>
                  </div>
                  <p className="settings-ai-message">{aiMessage}</p>
                  {aiRuntime.missing_env.length ? (
                    <p className="inline-error">
                      {t("settings.ai.missingEnv", { vars: aiRuntime.missing_env.join(", ") })}
                    </p>
                  ) : null}
                </section>

                <section className="settings-ai-card">
                  <div className="settings-ai-meta">
                    <span>{t("settings.ai.fields.lastChecked")}</span>
                    <strong>{aiRuntime.last_checked_at ?? "-"}</strong>
                  </div>
                  <div className="settings-ai-meta">
                    <span>{t("settings.ai.fields.checkedUrl")}</span>
                    <strong>{aiRuntime.checked_url ?? "-"}</strong>
                  </div>
                  <div className="chip-row">
                    {(aiRuntime.available_models.length ? aiRuntime.available_models : [aiRuntime.model_name]).map((model) => (
                      <span key={model} className="data-chip">
                        {model}
                      </span>
                    ))}
                  </div>
                </section>
              </div>

              {memberStatuses.length ? (
                <div className="settings-ai-member-list">
                  <h4>{locale === "ko" ? "추가 provider 연결" : "Additional provider connections"}</h4>
                  <div className="settings-ai-grid settings-ai-grid-secondary">
                    {memberStatuses.map((member) => {
                      const memberTone = member.connected ? "tone-success" : "tone-warning";
                      const memberAuthValue = member.auth_required
                        ? t(`settings.ai.boolean.${member.auth_configured ? "yes" : "no"}`)
                        : locale === "ko"
                          ? "필요 없음"
                          : "Not required";

                      return (
                        <section key={member.member_id} className="settings-ai-card">
                          <div className="settings-ai-head">
                            <div>
                              <p className="page-eyebrow">{member.role}</p>
                              <h3>{member.provider_label}</h3>
                            </div>
                            <span className={`status-pill ${memberTone}`}>
                              {t(`settings.ai.connection.${member.connected ? "connected" : "disconnected"}`)}
                            </span>
                          </div>
                          <div className="settings-ai-grid">
                            <div>
                              <span>{locale === "ko" ? "멤버" : "Member"}</span>
                              <strong>{member.member_id}</strong>
                            </div>
                            <div>
                              <span>{locale === "ko" ? "모델" : "Model"}</span>
                              <strong>{member.model_name}</strong>
                            </div>
                            <div>
                              <span>{t("settings.ai.fields.auth")}</span>
                              <strong>{t(`settings.ai.authType.${member.auth_type}`)}</strong>
                            </div>
                            <div>
                              <span>{authLabel}</span>
                              <strong>{memberAuthValue}</strong>
                            </div>
                          </div>
                          <p className="settings-ai-message">{getAiRuntimeMessage(locale, member)}</p>
                          <div className="settings-ai-meta">
                            <span>{t("settings.ai.fields.checkedUrl")}</span>
                            <strong>{member.checked_url ?? member.base_url}</strong>
                          </div>
                        </section>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="settings-section">
          <div className="section-header">
            <div>
              <h3>{t("settings.language.title")}</h3>
              <p>{t("settings.language.subtitle")}</p>
            </div>
          </div>
          <div className="locale-switcher" aria-label={t("settings.language.label")} role="group">
            <button
              aria-pressed={locale === "en"}
              className={`locale-button${locale === "en" ? " is-active" : ""}`}
              onClick={() => setLocale("en")}
              type="button"
            >
              {t("settings.language.en")}
            </button>
            <button
              aria-pressed={locale === "ko"}
              className={`locale-button${locale === "ko" ? " is-active" : ""}`}
              onClick={() => setLocale("ko")}
              type="button"
            >
              {t("settings.language.ko")}
            </button>
          </div>
        </div>

        <div className="settings-section">
          <div className="section-header">
            <div>
              <h3>{t("settings.data.title")}</h3>
              <p>{t("settings.data.subtitle")}</p>
            </div>
            <span className="status-pill">{t("settings.data.selectionCount", { count: selectionCount })}</span>
          </div>

          {ingestQuery.isLoading ? <p className="empty-state">{t("settings.data.loading")}</p> : null}
          {ingestQuery.isError ? <p className="inline-error">{t("settings.data.loadError")}</p> : null}

          {!ingestQuery.isLoading && !items.length ? <p className="empty-state">{t("settings.data.empty")}</p> : null}

          {items.length ? (
            <ul className="settings-ingest-list">
              {items.map((item) => {
                const title = item.metadata["doc_title"]?.toString() ?? item.filename ?? item.doc_id;

                return (
                  <li key={item.doc_id}>
                    <label className="settings-ingest-item">
                      <input
                        aria-label={t("settings.data.selectRecord", { docId: item.doc_id })}
                        checked={selectedDocIds.includes(item.doc_id)}
                        onChange={() => toggleDocId(item.doc_id)}
                        type="checkbox"
                      />
                      <span className="settings-ingest-copy">
                        <strong>{title}</strong>
                        <span>{item.doc_id}</span>
                        <span>{t("common.edgesExtracted", { count: item.edge_count })}</span>
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          ) : null}

          {feedback ? (
            <p aria-live="polite" className={deleteMutation.isError ? "inline-error" : "inline-note"}>
              {feedback}
            </p>
          ) : null}

          <div className="modal-actions">
            <button className="secondary-button" onClick={onClose} type="button">
              {t("settings.close")}
            </button>
            <button
              className="primary-button"
              disabled={!selectionCount || deleteMutation.isPending}
              onClick={handleDelete}
              type="button"
            >
              {deleteMutation.isPending ? t("settings.data.deletePending") : t("settings.data.delete")}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
};
