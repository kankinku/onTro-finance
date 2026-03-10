import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

import { App } from "../app/App";

describe("Council and ask", () => {
  test("shows cases and renders ask response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/api/council/cases")) {
          return new Response(
            JSON.stringify({
              cases: [{ case_id: "case_1", status: "OPEN", candidate_id: "rc_1" }],
            }),
          );
        }

        if (url.endsWith("/api/ask") && init?.method === "POST") {
          return new Response(
            JSON.stringify({
              answer: "Rates usually compress growth equity multiples in this graph.",
              confidence: 0.78,
              reasoning_used: true,
            }),
          );
        }

        return new Response(JSON.stringify({ items: [] }));
      }),
    );

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/council"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/case_1/i)).toBeInTheDocument());
    await user.type(screen.getByLabelText(/question/i), "금리와 성장주의 관계는?");
    await user.click(screen.getByRole("button", { name: /ask graph/i }));

    await waitFor(() => expect(screen.getByText(/compress growth equity multiples/i)).toBeInTheDocument());
    expect(screen.getByText(/0.78/)).toBeInTheDocument();
  });

  test("retries the selected case and reports the worker result", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/api/council/cases") && init?.method !== "POST") {
          return new Response(
            JSON.stringify({
              cases: [{ case_id: "case_1", status: "OPEN", candidate_id: "rc_1" }],
            }),
          );
        }

        if (url.endsWith("/api/council/cases/case_1/retry") && init?.method === "POST") {
          return new Response(
            JSON.stringify({
              case: { case_id: "case_1", status: "RETRYING" },
              result: { processed: 1, reopened: 1 },
            }),
          );
        }

        return new Response(JSON.stringify({ items: [] }));
      }),
    );

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/council"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/case_1/i)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /retry selected case/i }));

    await waitFor(() => expect(screen.getByText(/processed 1 pending case/i)).toBeInTheDocument());
  });

  test("allows manual council decision from the console", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/api/council/cases") && init?.method !== "POST") {
          return new Response(
            JSON.stringify({
              cases: [{ case_id: "case_1", status: "OPEN", candidate_id: "rc_1" }],
            }),
          );
        }

        if (url.endsWith("/api/council/cases/case_1/decision") && init?.method === "POST") {
          return new Response(
            JSON.stringify({
              case: { case_id: "case_1", status: "CLOSED" },
              candidate: { candidate_id: "rc_1", status: "COUNCIL_APPROVED" },
            }),
          );
        }

        return new Response(JSON.stringify({ items: [] }));
      }),
    );

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/council"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/case_1/i)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(screen.getByText(/COUNCIL_APPROVED/i)).toBeInTheDocument());
  });
});
