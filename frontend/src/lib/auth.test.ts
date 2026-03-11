import { afterEach, describe, expect, test } from "vitest";

import {
  buildAuthHeaders,
  clearAuthStorage,
  getActiveAuthProfile,
  setActiveAuthProfile,
  upsertAuthProfile,
} from "./auth";

describe("auth storage", () => {
  afterEach(() => {
    clearAuthStorage();
  });

  test("builds x-api-key headers from the active profile", () => {
    const profile = upsertAuthProfile({
      label: "operator key",
      mode: "api_key",
      secret: "operator-secret",
    });
    setActiveAuthProfile(profile.id);

    expect(getActiveAuthProfile()?.label).toBe("operator key");
    expect(buildAuthHeaders()).toEqual({ "x-api-key": "operator-secret" });
  });

  test("builds bearer authorization headers from the active profile", () => {
    const profile = upsertAuthProfile({
      label: "jwt",
      mode: "bearer",
      secret: "jwt-token",
    });
    setActiveAuthProfile(profile.id);

    expect(buildAuthHeaders()).toEqual({ Authorization: "Bearer jwt-token" });
  });
});
