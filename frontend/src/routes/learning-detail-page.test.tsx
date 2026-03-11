import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

import { App } from "../app/App";

describe("Learning detail", () => {
  test("loads learning product payload detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/learning/products/bundle/bundle-test.json")) {
          return new Response(
            JSON.stringify({
              kind: "bundle",
              file_name: "bundle-test.json",
              path: "/tmp/bundle-test.json",
              payload: { version: "bundle_v1", status: "DEPLOYED" },
            }),
          );
        }
        return new Response(JSON.stringify({ items: [] }));
      }),
    );

    render(
      <MemoryRouter initialEntries={["/learning/bundle/bundle-test.json"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/bundle-test.json/i)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/DEPLOYED/i)).toBeInTheDocument());
  });
});
