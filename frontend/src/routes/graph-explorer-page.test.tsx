import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

import { App } from "../app/App";

vi.mock("cytoscape", () => ({
  default: vi.fn(() => ({
    destroy: vi.fn(),
    on: vi.fn(),
    layout: vi.fn(() => ({ run: vi.fn() })),
    fit: vi.fn(),
  })),
}));

describe("Graph explorer", () => {
  test("searches entities and loads graph detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/entities")) {
          return new Response(
            JSON.stringify({
              items: [{ id: "Policy_Rate", label: "policy rate", kind: "domain", meta: { type: "MacroIndicator" } }],
            }),
          );
        }

        if (url.includes("/api/graph")) {
          return new Response(
            JSON.stringify({
              nodes: [
                { id: "Policy_Rate", label: "policy rate", kind: "domain", meta: { type: "MacroIndicator" } },
                { id: "Growth_Stocks", label: "growth stocks", kind: "domain", meta: { type: "AssetGroup" } },
              ],
              edges: [
                {
                  id: "rel_1",
                  source: "Policy_Rate",
                  target: "Growth_Stocks",
                  type: "pressures",
                  sign: "-",
                  confidence: 0.82,
                  origin: "council",
                },
              ],
            }),
          );
        }

        if (url.includes("/api/entities/Policy_Rate")) {
          return new Response(
            JSON.stringify({
              entity: { id: "Policy_Rate", label: "policy rate", kind: "domain", meta: { type: "MacroIndicator" } },
              neighbors: [{ relation_type: "pressures", target_label: "growth stocks", sign: "-" }],
            }),
          );
        }

        return new Response(JSON.stringify({ items: [] }));
      }),
    );

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/graph"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByLabelText(/entity search/i);
    await user.type(screen.getByLabelText(/entity search/i), "policy");
    await user.click(screen.getByRole("button", { name: /find entity/i }));
    await user.click(await screen.findByRole("button", { name: /policy rate/i }));

    await waitFor(() => expect(screen.getByText(/1 relation in view/i)).toBeInTheDocument());
    expect(screen.getByText(/pressures/i)).toBeInTheDocument();
    expect(screen.getByText(/growth stocks/i)).toBeInTheDocument();
  });
});
