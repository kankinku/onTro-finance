import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

import { App } from "../app/App";

describe("Saved data", () => {
  test("shows ingest detail when doc query is present", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/ingests?")) {
          return new Response(
            JSON.stringify({
              items: [{ doc_id: "doc_001", input_type: "text", edge_count: 2, metadata: { doc_title: "Macro note" } }],
            }),
          );
        }

        if (url.includes("/api/ingests/doc_001")) {
          return new Response(
            JSON.stringify({
              doc_id: "doc_001",
              input_type: "text",
              edge_count: 2,
              destinations: { domain: 1, personal: 0, council: 1 },
              metadata: { doc_title: "Macro note" },
              council_case_ids: ["case_1"],
            }),
          );
        }

        return new Response(JSON.stringify({ items: [] }));
      }),
    );

    render(
      <MemoryRouter initialEntries={["/saved?doc=doc_001"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/macro note/i)).toBeInTheDocument());
    expect(screen.getByText(/case_1/i)).toBeInTheDocument();
    expect(screen.getByText(/2 edges extracted/i)).toBeInTheDocument();
  });
});
