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

        if (url.includes("/api/documents?") || url.endsWith("/api/documents")) {
          return new Response(
            JSON.stringify({
              items: [
                {
                  doc_id: "doc_001",
                  title: "Macro note",
                  edge_count: 2,
                  metadata: { doc_title: "Macro note" },
                },
              ],
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

        if (url.includes("/api/documents/doc_001/graph")) {
          return new Response(
            JSON.stringify({
              nodes: [{ id: "Policy_Rate", label: "Policy_Rate", kind: "domain", meta: {} }],
              edges: [{ id: "e1", source: "Policy_Rate", target: "Growth_Stocks", type: "pressures" }],
            }),
          );
        }

        if (url.includes("/api/documents/doc_001/structure")) {
          return new Response(
            JSON.stringify({
              doc_id: "doc_001",
              structured_sections: [{ chapter_title: "Chapter 1", section_title: "1.1 Rates" }],
              pdf_blocks: [{ page_number: 2, block_type: "ocr_needed", ocr_required: true }],
              ocr_needed_pages: [2],
              table_blocks: [{ page_number: 1, caption: "Scenario Table" }],
              consolidated_relations: [],
            }),
          );
        }

        if (url.includes("/api/documents/doc_001")) {
          return new Response(
            JSON.stringify({
              doc_id: "doc_001",
              title: "Macro note",
              author: "Analyst",
              institution: "Macro Lab",
              source_type: "research_note",
              edge_count: 2,
              destinations: { domain: 1, personal: 0, council: 1 },
              metadata: { doc_title: "Macro note" },
              council_case_ids: ["case_1"],
              related_relations: [
                {
                  head_entity_id: "Policy_Rate",
                  relation_type: "pressures",
                  tail_entity_id: "Growth_Stocks",
                  destinations: ["domain", "council"],
                  evidence_count: 2,
                  max_confidence: 0.93,
                  time_scopes: ["short_term"],
                  semantic_tags: ["macro_impact"],
                  council_case_ids: ["case_1"],
                },
              ],
              evidence: {
                validation_events: [
                  {
                    edge_id: "edge_1",
                    relation_type: "pressures",
                    fragment_text: "Higher rates pressure growth stocks.",
                    destination: "domain",
                    time_scope: "short_term",
                  },
                ],
                council_events: [
                  {
                    event_type: "council_final",
                    relation_type: "pressures",
                    citation_text: "Higher rates pressure growth stocks.",
                    time_scope: "short_term",
                  },
                ],
                counts: { validation: 1, council: 1, unique_relations: 1 },
              },
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

    await waitFor(() => expect(screen.getAllByText(/macro note/i).length).toBeGreaterThan(0));
    expect(screen.getByText(/case_1/i)).toBeInTheDocument();
    expect(screen.getAllByText(/2 edges extracted/i)).toHaveLength(2);
    expect(screen.getByRole("heading", { name: /linked relations/i })).toBeInTheDocument();
    expect(screen.getByText(/policy_rate - pressures - growth_stocks/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /evidence trail/i })).toBeInTheDocument();
    expect(screen.getByText(/document structure/i)).toBeInTheDocument();
    expect(screen.getByText(/scenario table/i)).toBeInTheDocument();
    expect(screen.getByText(/document subgraph/i)).toBeInTheDocument();
  });
});
