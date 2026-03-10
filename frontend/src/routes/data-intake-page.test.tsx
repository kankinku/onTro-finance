import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

import { App } from "../app/App";

describe("Data intake", () => {
  test("submits text input and shows ingest result", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/text/add-to-vectordb") && init?.method === "POST") {
          return new Response(
            JSON.stringify({
              doc_id: "doc_001",
              edge_count: 8,
              destinations: { domain: 3, personal: 2, council: 3 },
              council_case_ids: ["case_9"],
            }),
          );
        }

        return new Response(JSON.stringify({ items: [] }));
      }),
    );

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/intake"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByLabelText(/analysis text/i);
    await user.type(screen.getByLabelText(/analysis text/i), "Rates are falling and cyclicals respond.");
    await user.click(screen.getByRole("button", { name: /submit text/i }));

    await waitFor(() => expect(screen.getByText("doc_001")).toBeInTheDocument());
    expect(screen.getByText(/case_9/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open saved record/i })).toHaveAttribute("href", "/saved?doc=doc_001");
  });

  test("uploads a pdf and shows ingest result", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/pdf/extract-and-embed") && init?.method === "POST") {
          return new Response(
            JSON.stringify({
              doc_id: "pdf_001",
              edge_count: 14,
              destinations: { domain: 9, personal: 1, council: 4 },
              council_case_ids: ["case_pdf"],
            }),
          );
        }

        return new Response(JSON.stringify({ items: [] }));
      }),
    );

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/intake"]}>
        <App />
      </MemoryRouter>,
    );

    const file = new File(["%PDF-1.4 sample"], "macro.pdf", { type: "application/pdf" });
    await screen.findByLabelText(/pdf file/i);
    await user.upload(screen.getByLabelText(/pdf file/i), file);
    await user.click(screen.getByRole("button", { name: /submit pdf/i }));

    await waitFor(() => expect(screen.getByText("pdf_001")).toBeInTheDocument());
    expect(screen.getByText(/case_pdf/i)).toBeInTheDocument();
  });
});
