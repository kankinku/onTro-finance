import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

import { App } from "./App";

describe("App shell", () => {
  test("renders overview data from dashboard summary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/dashboard/summary")) {
          return new Response(
            JSON.stringify({
              status: "ready",
              totals: { ingests: 12, entities: 84, relations: 128 },
              council: { pending: 3, closed: 11, available_members: 5 },
              recent_ingests: [],
              recent_errors: [],
            }),
          );
        }

        return new Response(JSON.stringify({ items: [] }));
      }),
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: /overview/i })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("84")).toBeInTheDocument());
    expect(screen.getByText(/relations tracked/i)).toBeInTheDocument();
  });
});
