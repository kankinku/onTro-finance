import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

import { App } from "./App";

describe("App shell", () => {
  test("opens settings, switches locales, and deletes selected ingest records", async () => {
    let ingests = [
      {
        doc_id: "doc_001",
        input_type: "text",
        edge_count: 2,
        metadata: { doc_title: "Macro note" },
      },
      {
        doc_id: "doc_002",
        input_type: "pdf",
        edge_count: 1,
        metadata: { doc_title: "Rates deck" },
      },
    ];

    let aiRuntime = {
      provider: "ollama",
      provider_label: "Ollama",
      model_name: "llama3.2:latest",
      base_url: "http://localhost:11434",
      auth_type: "none",
      auth_required: false,
      auth_configured: true,
      connected: false,
      status: "disconnected",
      message: "connection refused",
      checked_url: "http://localhost:11434/api/tags",
      available_models: ["llama3.2:latest"],
      missing_env: [],
      last_checked_at: "2026-03-09T16:30:00",
      attempts: 1,
      members: [
        {
          member_id: "proposer-openai",
          role: "proposer",
          provider: "openai_gpt_sdk",
          provider_label: "OpenAI GPT SDK",
          model_name: "gpt-4.1",
          base_url: "https://api.openai.com/v1",
          auth_type: "api_key",
          auth_required: true,
          auth_configured: false,
          connected: false,
          status: "disconnected",
          message: "missing required environment variables",
          checked_url: "https://api.openai.com/v1/models",
          available_models: [],
          missing_env: ["OPENAI_API_KEY"],
          attempts: 1,
        },
        {
          member_id: "challenger-copilot",
          role: "challenger",
          provider: "github_copilot_oauth_app",
          provider_label: "GitHub Copilot OAuth App",
          model_name: "copilot-gpt",
          base_url: "https://copilot.example.internal",
          auth_type: "oauth_app",
          auth_required: true,
          auth_configured: false,
          connected: false,
          status: "disconnected",
          message: "missing required environment variables",
          checked_url: "https://copilot.example.internal/models",
          available_models: [],
          missing_env: ["GITHUB_COPILOT_ACCESS_TOKEN"],
          attempts: 1,
        },
      ],
    };

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);

        if (url.endsWith("/api/dashboard/summary")) {
          return new Response(
            JSON.stringify({
              status: "ready",
              ready: true,
              totals: {
                ingests: ingests.length,
                documents: ingests.length,
                entities: 84,
                relations: 128,
                edges: 128,
                domain_relations: 64,
                personal_relations: 64,
                council_pending: 3,
                council_closed: 11,
              },
              council: { pending: 3, closed: 11, available_members: 5 },
              trust: {
                candidate_status_counts: { COUNCIL_PENDING: 3, COUNCIL_APPROVED: 2 },
                trigger_reason_counts: { LOW_CONFIDENCE: 2, HIGH_IMPACT_RELATION: 1 },
                validation_destination_counts: { domain: 4, council: 3 },
                confidence_bands: { low: 1, medium: 4, high: 6 },
              },
              learning: {
                counts: { snapshots: 2, evaluations: 1, bundles: 1, goldsets: 1 },
                items: [
                  { kind: "snapshot", file_name: "dataset-v1.json", version: "ds_v1", task_type: "relation" },
                  { kind: "evaluation", file_name: "evaluation-v1.json", dataset_version: "ds_v1", goldset_version: "gold_v1" },
                ],
              },
              audit: {
                count: 1,
                items: [{ action: "post", path: "/api/learning/evaluations/run", client: "127.0.0.1" }],
              },
              system: {
                storage_backend: "inmemory",
                storage_ok: true,
                llm_available: false,
                council_worker_active: false,
                last_council_run: null,
                council_last_error: null,
              },
              recent_ingests: ingests,
              event_backlog: {},
            }),
          );
        }

        if (url.includes("/api/ingests?")) {
          return new Response(JSON.stringify({ items: ingests }));
        }

        if (url.endsWith("/api/system/ai-runtime")) {
          return new Response(JSON.stringify(aiRuntime));
        }

        if (url.endsWith("/api/system/ai-runtime/check")) {
          aiRuntime = {
            ...aiRuntime,
            connected: true,
            status: "connected",
            message: "ok",
            attempts: 2,
            members: aiRuntime.members.map((member) => ({
              ...member,
              auth_configured: true,
              connected: true,
              status: "connected",
              message: "ok",
              missing_env: [],
              attempts: 2,
            })),
          };
          return new Response(JSON.stringify(aiRuntime));
        }

        if (url.endsWith("/api/ingests/delete")) {
          const payload = JSON.parse(String(init?.body ?? "{}")) as { doc_ids?: string[] };
          ingests = ingests.filter((item) => !payload.doc_ids?.includes(item.doc_id));
          return new Response(
            JSON.stringify({
              status: "success",
              deleted_doc_ids: payload.doc_ids ?? [],
              remaining_ingests: ingests.length,
            }),
          );
        }

        if (url.endsWith("/api/learning/evaluations/run")) {
          const payload = JSON.parse(String(init?.body ?? "{}"));
          expect(payload.goldset_filename).toBe("custom-gold.json");
          expect(payload.snapshot_filename).toBe("custom-snapshot.json");
          return new Response(
            JSON.stringify({
              snapshot_filename: "dataset-test.json",
              goldset_filename: "gold-test.json",
              evaluation_filename: "evaluation-output.json",
              metrics: { f1: 0.81 },
            }),
          );
        }

        if (url.endsWith("/api/learning/bundles/promote")) {
          const payload = JSON.parse(String(init?.body ?? "{}"));
          expect(payload.bundle_filename).toBe("custom-bundle.json");
          return new Response(JSON.stringify({ status: "DEPLOYED", review_notes: "Promoted from console" }));
        }

        if (url.includes("/api/audit/logs")) {
          return new Response(
            JSON.stringify({ count: 1, items: [{ action: "post", path: "/api/council/process-pending", client: "127.0.0.1" }] }),
          );
        }

        return new Response(JSON.stringify({ items: [] }));
      }),
    );

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: /overview/i });
    expect(screen.getByRole("heading", { name: /overview/i })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("84")).toBeInTheDocument());
    expect(screen.getByText(/trust signals/i)).toBeInTheDocument();
    expect(screen.getByText(/learning products/i)).toBeInTheDocument();
    expect(screen.getByText(/audit trail/i)).toBeInTheDocument();
    await user.clear(screen.getByPlaceholderText(/goldset filename/i));
    await user.type(screen.getByPlaceholderText(/goldset filename/i), "custom-gold.json");
    await user.clear(screen.getByPlaceholderText(/snapshot filename/i));
    await user.type(screen.getByPlaceholderText(/snapshot filename/i), "custom-snapshot.json");
    await user.clear(screen.getByPlaceholderText(/bundle filename/i));
    await user.type(screen.getByPlaceholderText(/bundle filename/i), "custom-bundle.json");
    await user.click(screen.getByRole("button", { name: /run evaluation/i }));
    await user.click(screen.getByRole("button", { name: /promote bundle/i }));
    await user.type(screen.getByPlaceholderText(/filter action/i), "post");

    await user.click(screen.getByRole("button", { name: /settings/i }));

    const dialog = screen.getByRole("dialog", { name: /settings/i });
    expect(within(dialog).getByText(/choose the interface language/i)).toBeInTheDocument();
    expect(within(dialog).getAllByText("llama3.2:latest").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText("Disconnected").length).toBeGreaterThan(0);
    expect(within(dialog).getByText("OpenAI GPT SDK")).toBeInTheDocument();
    expect(within(dialog).getByText("GitHub Copilot OAuth App")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: /check connection/i }));
    await waitFor(() => expect(within(dialog).getAllByText("Connected").length).toBeGreaterThan(0));

    await user.click(within(dialog).getByRole("checkbox", { name: /doc_001/ }));
    await user.click(within(dialog).getByRole("button", { name: /delete selected/i }));

    await waitFor(() =>
      expect(within(dialog).getByText(/deleted 1 selected record/i)).toBeInTheDocument(),
    );
    await waitFor(() => expect(within(dialog).queryByText("Macro note")).not.toBeInTheDocument());

    const localeGroup = within(dialog).getByRole("group", { name: /language selector/i });
    await user.click(within(localeGroup).getAllByRole("button")[1]);

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: /overview/i })).not.toBeInTheDocument(),
    );
    expect(within(dialog).queryByText(/choose the interface language/i)).not.toBeInTheDocument();
    expect(within(dialog).queryByText("AI Runtime")).not.toBeInTheDocument();
  });
});
