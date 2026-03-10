import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { CytoscapeCanvas } from "../components/CytoscapeCanvas";
import { SectionCard } from "../components/SectionCard";
import { getGraph, searchEntities } from "../lib/api";

const EMPTY_GRAPH = { nodes: [], edges: [] };

export const GraphExplorerPage = () => {
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
          <p className="page-eyebrow">Graph Inspection</p>
          <h1>Graph Explorer</h1>
          <p>Search an entity, load a local subgraph, and review the relation story in one workspace.</p>
        </div>
      </header>

      <SectionCard title="Search" subtitle="Start from a named entity or indicator.">
        <div className="search-row">
          <label className="field-label compact" htmlFor="entity-search">
            Entity search
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
            <option value={1}>Depth 1</option>
            <option value={2}>Depth 2</option>
            <option value={3}>Depth 3</option>
          </select>
          <button className="primary-button" onClick={() => setSearchTerm(searchInput.trim())} type="button">
            Find entity
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
        <SectionCard title="Subgraph" subtitle={`${graphQuery.data?.edges.length ?? 0} relation in view`}>
          <CytoscapeCanvas graph={graphQuery.data ?? EMPTY_GRAPH} />
        </SectionCard>

        <SectionCard title="Entity Detail" subtitle="Focused context for the selected node.">
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
                  <li className="empty-state">No adjacent relations are loaded yet.</li>
                )}
              </ul>
            </div>
          ) : (
            <p className="empty-state">Search and select an entity to inspect its graph footprint.</p>
          )}
        </SectionCard>
      </div>
    </div>
  );
};
