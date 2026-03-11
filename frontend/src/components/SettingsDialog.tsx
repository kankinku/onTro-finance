import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useI18n } from "../app/i18n";
import { checkAiRuntimeStatus, deleteIngests, getAiRuntimeStatus, getIngests, probeAuthProfile } from "../lib/api";
import {
  deleteAuthProfile,
  getActiveAuthProfileId,
  listAuthProfiles,
  maskSecret,
  setActiveAuthProfile,
  upsertAuthProfile,
  type AuthProfile,
  type AuthProfileMode,
} from "../lib/auth";
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
      ? "Ollama 서버가 실행 중이 아니거나 localhost:11434 연결이 닫혀 있습니다. Ollama 앱을 실행하거나 `ollama serve`를 먼저 실행하세요."
      : "Ollama is not running or localhost:11434 is closed. Start the Ollama app or run `ollama serve` first.";
  }

  return aiRuntime.message;
};

export const SettingsDialog = ({ isOpen, onClose }: SettingsDialogProps) => {
  const { locale, setLocale, t } = useI18n();
  const queryClient = useQueryClient();
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [authProfiles, setAuthProfiles] = useState<AuthProfile[]>([]);
  const [activeAuthProfileId, setActiveAuthProfileId] = useState<string | null>(null);
  const [authLabel, setAuthLabel] = useState("");
  const [authSecret, setAuthSecret] = useState("");
  const [authMode, setAuthMode] = useState<AuthProfileMode>("api_key");
  const [editingAuthProfileId, setEditingAuthProfileId] = useState<string | null>(null);
  const [authFeedback, setAuthFeedback] = useState<string | null>(null);

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

  useEffect(() => {
    if (!isOpen) {
      setAuthFeedback(null);
      setEditingAuthProfileId(null);
      setAuthLabel("");
      setAuthSecret("");
      setAuthMode("api_key");
      return;
    }

    setAuthProfiles(listAuthProfiles());
    setActiveAuthProfileId(getActiveAuthProfileId());
  }, [isOpen]);

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
  const authProbeMutation = useMutation({
    mutationFn: probeAuthProfile,
    onSuccess: async (payload) => {
      const countLabel =
        locale === "ko"
          ? `문서 ${payload.count}건 접근 가능`
          : `Access confirmed (${payload.count} document visible)`;
      setAuthFeedback(countLabel);
      await queryClient.invalidateQueries();
    },
    onError: (error) => {
      setAuthFeedback(getErrorMessage(error, locale === "ko" ? "인증 확인에 실패했습니다." : "Authentication check failed."));
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
  const aiAuthConfiguredLabel = aiRuntime?.auth_required
    ? t("settings.ai.fields.authConfigured")
    : locale === "ko"
      ? "인증 필요 여부"
      : "Authentication";
  const aiAuthConfiguredValue = aiRuntime?.auth_required
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

  const syncAuthProfiles = () => {
    setAuthProfiles(listAuthProfiles());
    setActiveAuthProfileId(getActiveAuthProfileId());
  };

  const resetAuthForm = () => {
    setEditingAuthProfileId(null);
    setAuthLabel("");
    setAuthSecret("");
    setAuthMode("api_key");
  };

  const handleSaveAuthProfile = async () => {
    if (!authLabel.trim() || !authSecret.trim()) {
      setAuthFeedback(locale === "ko" ? "프로필 이름과 비밀값이 필요합니다." : "Profile label and secret are required.");
      return;
    }

    const saved = upsertAuthProfile({
      id: editingAuthProfileId ?? undefined,
      label: authLabel,
      mode: authMode,
      secret: authSecret,
    });
    if (!activeAuthProfileId) {
      setActiveAuthProfile(saved.id);
    }
    syncAuthProfiles();
    resetAuthForm();
    setAuthFeedback(locale === "ko" ? "인증 프로필을 저장했습니다." : "Authentication profile saved.");
    await queryClient.invalidateQueries();
  };

  const handleActivateAuthProfile = async (profileId: string | null) => {
    setActiveAuthProfile(profileId);
    syncAuthProfiles();
    setAuthFeedback(
      profileId
        ? locale === "ko"
          ? "활성 인증 프로필을 변경했습니다."
          : "Active authentication profile updated."
        : locale === "ko"
          ? "인증 헤더를 사용하지 않도록 변경했습니다."
          : "Authentication headers disabled.",
    );
    await queryClient.invalidateQueries();
  };

  const handleEditAuthProfile = (profile: AuthProfile) => {
    setEditingAuthProfileId(profile.id);
    setAuthLabel(profile.label);
    setAuthSecret(profile.secret);
    setAuthMode(profile.mode);
    setAuthFeedback(null);
  };

  const handleDeleteAuthProfile = async (profileId: string) => {
    deleteAuthProfile(profileId);
    syncAuthProfiles();
    if (editingAuthProfileId === profileId) {
      resetAuthForm();
    }
    setAuthFeedback(locale === "ko" ? "인증 프로필을 삭제했습니다." : "Authentication profile deleted.");
    await queryClient.invalidateQueries();
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
              <h3>{locale === "ko" ? "인증" : "Authentication"}</h3>
              <p>
                {locale === "ko"
                  ? "OpenClaw onboard 방식처럼 브라우저 안에 여러 인증 프로필을 저장하고, 활성 프로필의 헤더를 모든 API 요청에 자동 적용합니다."
                  : "Store multiple auth profiles locally, then apply the active profile header to every API request."}
              </p>
            </div>
          </div>

          <div className="settings-ai-grid settings-ai-grid-secondary">
            <section className="settings-ai-card">
              <div className="settings-ai-meta">
                <span>{locale === "ko" ? "활성 상태" : "Active state"}</span>
                <strong>
                  {activeAuthProfileId
                    ? locale === "ko"
                      ? "사용 중"
                      : "Enabled"
                    : locale === "ko"
                      ? "사용 안 함"
                      : "Disabled"}
                </strong>
              </div>
              <div className="settings-auth-form">
                <input
                  className="inline-input"
                  placeholder={locale === "ko" ? "프로필 이름" : "Profile label"}
                  value={authLabel}
                  onChange={(event) => setAuthLabel(event.target.value)}
                />
                <select
                  aria-label={locale === "ko" ? "인증 방식" : "Auth mode"}
                  className="inline-input select-input"
                  value={authMode}
                  onChange={(event) => setAuthMode(event.target.value as AuthProfileMode)}
                >
                  <option value="api_key">{locale === "ko" ? "API 키 (x-api-key)" : "API key (x-api-key)"}</option>
                  <option value="bearer">{locale === "ko" ? "Bearer 토큰" : "Bearer token"}</option>
                </select>
                <input
                  className="inline-input"
                  placeholder={locale === "ko" ? "비밀값 또는 토큰" : "Secret or token"}
                  type="password"
                  value={authSecret}
                  onChange={(event) => setAuthSecret(event.target.value)}
                />
                <div className="chip-row">
                  <button className="primary-button" onClick={() => void handleSaveAuthProfile()} type="button">
                    {editingAuthProfileId
                      ? locale === "ko"
                        ? "프로필 수정"
                        : "Update profile"
                      : locale === "ko"
                        ? "프로필 저장"
                        : "Save profile"}
                  </button>
                  <button className="secondary-button" onClick={resetAuthForm} type="button">
                    {locale === "ko" ? "폼 초기화" : "Reset form"}
                  </button>
                  <button
                    className="secondary-button"
                    disabled={authProbeMutation.isPending}
                    onClick={() => authProbeMutation.mutate()}
                    type="button"
                  >
                    {authProbeMutation.isPending
                      ? locale === "ko"
                        ? "확인 중..."
                        : "Checking..."
                      : locale === "ko"
                        ? "인증 테스트"
                        : "Test auth"}
                  </button>
                </div>
              </div>
              <p className="settings-ai-message">
                {locale === "ko"
                  ? "API 키는 x-api-key로, OIDC 또는 JWT 토큰은 Authorization: Bearer로 전송합니다."
                  : "API keys use x-api-key. OIDC or JWT tokens use Authorization: Bearer."}
              </p>
            </section>

            <section className="settings-ai-card">
              <div className="settings-ai-meta">
                <span>{locale === "ko" ? "저장된 프로필" : "Stored profiles"}</span>
                <strong>{authProfiles.length}</strong>
              </div>
              {authProfiles.length ? (
                <ul className="settings-auth-profile-list">
                  {authProfiles.map((profile) => (
                    <li key={profile.id} className={`settings-auth-profile${activeAuthProfileId === profile.id ? " is-active" : ""}`}>
                      <div className="settings-auth-profile-copy">
                        <strong>{profile.label}</strong>
                        <span>{profile.mode === "api_key" ? "x-api-key" : "Bearer"} · {maskSecret(profile.secret)}</span>
                      </div>
                      <div className="chip-row">
                        <button className="secondary-button" onClick={() => handleEditAuthProfile(profile)} type="button">
                          {locale === "ko" ? "편집" : "Edit"}
                        </button>
                        <button className="secondary-button" onClick={() => void handleActivateAuthProfile(profile.id)} type="button">
                          {activeAuthProfileId === profile.id
                            ? locale === "ko"
                              ? "활성"
                              : "Active"
                            : locale === "ko"
                              ? "활성화"
                              : "Activate"}
                        </button>
                        <button className="secondary-button" onClick={() => void handleDeleteAuthProfile(profile.id)} type="button">
                          {locale === "ko" ? "삭제" : "Delete"}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="empty-state">{locale === "ko" ? "저장된 인증 프로필이 없습니다." : "No auth profiles stored yet."}</p>
              )}
              <div className="chip-row">
                <button className="secondary-button" onClick={() => void handleActivateAuthProfile(null)} type="button">
                  {locale === "ko" ? "인증 비활성화" : "Disable auth"}
                </button>
              </div>
            </section>
          </div>

          {authFeedback ? <p className="inline-note">{authFeedback}</p> : null}
        </div>

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
                    <span>{aiAuthConfiguredLabel}</span>
                    <span className={`status-pill ${authTone}`}>{aiAuthConfiguredValue}</span>
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
                              <span>{aiAuthConfiguredLabel}</span>
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
