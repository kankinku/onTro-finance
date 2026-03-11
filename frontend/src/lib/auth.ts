export type AuthProfileMode = "api_key" | "bearer";

export interface AuthProfile {
  id: string;
  label: string;
  mode: AuthProfileMode;
  secret: string;
  createdAt: string;
  updatedAt: string;
}

const AUTH_PROFILES_KEY = "ontro-finance-auth-profiles";
const ACTIVE_AUTH_PROFILE_KEY = "ontro-finance-active-auth-profile";

const canUseStorage = () => typeof window !== "undefined" && typeof window.localStorage !== "undefined";

const nowIso = () => new Date().toISOString();

const randomId = () => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  return `auth_${Date.now().toString(36)}`;
};

const readRawProfiles = (): AuthProfile[] => {
  if (!canUseStorage()) {
    return [];
  }

  const raw = window.localStorage.getItem(AUTH_PROFILES_KEY);
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw) as AuthProfile[];
    return Array.isArray(parsed) ? parsed.filter((item) => item?.id && item?.secret) : [];
  } catch {
    return [];
  }
};

const writeProfiles = (profiles: AuthProfile[]) => {
  if (!canUseStorage()) {
    return;
  }

  window.localStorage.setItem(AUTH_PROFILES_KEY, JSON.stringify(profiles));
};

export const listAuthProfiles = (): AuthProfile[] => readRawProfiles();

export const getActiveAuthProfileId = (): string | null => {
  if (!canUseStorage()) {
    return null;
  }

  return window.localStorage.getItem(ACTIVE_AUTH_PROFILE_KEY);
};

export const getActiveAuthProfile = (): AuthProfile | null => {
  const activeId = getActiveAuthProfileId();
  if (!activeId) {
    return null;
  }

  return readRawProfiles().find((profile) => profile.id === activeId) ?? null;
};

export const setActiveAuthProfile = (profileId: string | null) => {
  if (!canUseStorage()) {
    return;
  }

  if (!profileId) {
    window.localStorage.removeItem(ACTIVE_AUTH_PROFILE_KEY);
    return;
  }

  window.localStorage.setItem(ACTIVE_AUTH_PROFILE_KEY, profileId);
};

export const upsertAuthProfile = (input: {
  id?: string;
  label: string;
  mode: AuthProfileMode;
  secret: string;
}): AuthProfile => {
  const profiles = readRawProfiles();
  const existing = input.id ? profiles.find((profile) => profile.id === input.id) : null;
  const profile: AuthProfile = {
    id: existing?.id ?? randomId(),
    label: input.label.trim(),
    mode: input.mode,
    secret: input.secret.trim(),
    createdAt: existing?.createdAt ?? nowIso(),
    updatedAt: nowIso(),
  };

  const nextProfiles = existing
    ? profiles.map((item) => (item.id === profile.id ? profile : item))
    : [profile, ...profiles];
  writeProfiles(nextProfiles);

  if (!getActiveAuthProfileId()) {
    setActiveAuthProfile(profile.id);
  }

  return profile;
};

export const deleteAuthProfile = (profileId: string) => {
  const nextProfiles = readRawProfiles().filter((profile) => profile.id !== profileId);
  writeProfiles(nextProfiles);

  if (getActiveAuthProfileId() === profileId) {
    setActiveAuthProfile(nextProfiles[0]?.id ?? null);
  }
};

export const buildAuthHeaders = (): Record<string, string> => {
  const profile = getActiveAuthProfile();
  if (!profile) {
    return {};
  }

  if (profile.mode === "api_key") {
    return { "x-api-key": profile.secret };
  }

  return { Authorization: `Bearer ${profile.secret}` };
};

export const maskSecret = (secret: string): string => {
  if (secret.length <= 8) {
    return "*".repeat(secret.length);
  }

  return `${secret.slice(0, 4)}...${secret.slice(-4)}`;
};

export const clearAuthStorage = () => {
  if (!canUseStorage()) {
    return;
  }

  window.localStorage.removeItem(AUTH_PROFILES_KEY);
  window.localStorage.removeItem(ACTIVE_AUTH_PROFILE_KEY);
};
