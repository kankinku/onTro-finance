import { useQuery } from "@tanstack/react-query";
import { Suspense, lazy, useEffect, useMemo, useState } from "react";

import { useI18n } from "../app/i18n";
import { SectionCard } from "../components/SectionCard";
import { getGraph, searchEntities } from "../lib/api";

const EMPTY_GRAPH = { nodes: [], edges: [] };
const CytoscapeCanvas = lazy(async () =>
  import("../components/CytoscapeCanvas").then((module) => ({ default: module.CytoscapeCanvas })),
);

export const GraphExplorerPage = () => {
  const { t } = useI18n();
  const [searchInput, setSearchInput] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [depth, setDepth] = useState(1);

  const entityQuery = useQuery({
    queryKey: ["entities", searchTerm],
    queryFn: () => searchEntities(searchTerm),
    enabled: Boolean(searchTerm),
  });

  useEffect(() => {
    setSelectedEntityId(null);
  }, [searchTerm]);

  useEffect(() => {
    if (entityQuery.data?.items.length) {
      setSelectedEntityId(entityQuery.data.items[0].id);
    }
  }, [entityQuery.data]);

  const graphQuery = useQuery({
    queryKey: ["graph", selectedEntityId, depth],
    queryFn: () => getGraph(selectedEntityId ?? "", depth),
    enabled: Boolean(selectedEntityId),
  });

  const selectedNode = useMemo(
    () => graphQuery.data?.nodes.find((node) => node.id === selectedEntityId) ?? null,
    [graphQuery.data, selectedEntityId],
  );

  const relatedEdges = useMemo(
    () =>
      graphQuery.data?.edges.filter(
        (edge) => edge.source === selectedEntityId || edge.target === selectedEntityId,
      ) ?? [],
    [graphQuery.data, selectedEntityId],
  );

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="page-eyebrow">{t("graph.eyebrow")}</p>
          <h1>{t("graph.title")}</h1>
          <p>{t("graph.description")}</p>
        </div>
      </header>

      <SectionCard title={t("graph.search.title")} subtitle={t("graph.search.subtitle")}>
        <div className="search-row">
          <label className="field-label compact" htmlFor="entity-search">
            {t("graph.search.label")}
          </label>
          <input
            id="entity-search"
            className="inline-input"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter") setSearchTerm(searchInput.trim()); }}
          />
          <select
            className="inline-input select-input"
            value={depth}
            onChange={(event) => setDepth(Number(event.target.value))}
          >
            <option value={1}>{t("graph.depth.one")}</option>
            <option value={2}>{t("graph.depth.two")}</option>
            <option value={3}>{t("graph.depth.three")}</option>
          </select>
          <button className="primary-button" onClick={() => setSearchTerm(searchInput.trim())} type="button">
            {t("graph.search.button")}
          </button>
        </div>
        <div className="chip-row">
          {entityQuery.data?.items.map((entity) => (
            <button
              key={entity.id}
              className={`entity-button${selectedEntityId === entity.id ? " is-selected" : ""}`}
              onClick={() => setSelectedEntityId(entity.id)}
              type="button"
            >
              {entity.label}
            </button>
          ))}
        </div>
      </SectionCard>

      <div className="content-grid graph-grid">
        <SectionCard
          title={t("graph.subgraph.title")}
          subtitle={t("graph.subgraph.subtitle", { count: graphQuery.data?.edges.length ?? 0 })}
        >
          <Suspense fallback={<p className="empty-state">Loading graph...</p>}>
            <CytoscapeCanvas graph={graphQuery.data ?? EMPTY_GRAPH} />
          </Suspense>
        </SectionCard>

        <SectionCard title={t("graph.detail.title")} subtitle={t("graph.detail.subtitle")}>
          {selectedNode ? (
            <div className="detail-stack">
              <h3>{selectedNode.label}</h3>
              <p>{selectedNode.meta.type?.toString() ?? selectedNode.kind}</p>
              <ul className="data-list">
                {relatedEdges.length ? (
                  relatedEdges.map((edge) => {
                    const counterparty =
                      graphQuery.data?.nodes.find((node) =>
                        node.id === (edge.source === selectedEntityId ? edge.target : edge.source),
                      )?.label ?? edge.target;

                    return (
                      <li key={edge.id}>
                        <strong>{edge.type}</strong>
                        <span>
                          {counterparty}
                          {edge.sign ? ` (${edge.sign})` : ""}
                        </span>
                      </li>
                    );
                  })
                ) : (
                  <li className="empty-state">{t("graph.detail.noRelations")}</li>
                )}
              </ul>
            </div>
          ) : (
            <p className="empty-state">{t("graph.detail.empty")}</p>
          )}
        </SectionCard>
      </div>
    </div>
  );
};
