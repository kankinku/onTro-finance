import cytoscape from "cytoscape";
import { useEffect, useRef } from "react";

import type { GraphResponse } from "../lib/types";

interface CytoscapeCanvasProps {
  graph: GraphResponse;
}

export const CytoscapeCanvas = ({ graph }: CytoscapeCanvasProps) => {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current || graph.nodes.length === 0) {
      return undefined;
    }

    const instance = cytoscape({
      container: containerRef.current,
      elements: [
        ...graph.nodes.map((node) => ({
          data: { id: node.id, label: node.label, kind: node.kind },
        })),
        ...graph.edges.map((edge) => ({
          data: {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            label: edge.type,
            sign: edge.sign ?? "",
          },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#174c46",
            label: "data(label)",
            color: "#f3eee2",
            "font-size": "11px",
            "text-wrap": "wrap",
            "text-max-width": "100px",
          },
        },
        {
          selector: "edge",
          style: {
            "line-color": "#d97043",
            "target-arrow-color": "#d97043",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": "9px",
            color: "#65584a",
          },
        },
      ],
      layout: { name: "cose", animate: false, padding: 24 },
    });

    instance.fit(undefined, 24);

    return () => {
      instance.destroy();
    };
  }, [graph]);

  if (graph.nodes.length === 0) {
    return <div className="graph-placeholder">Select an entity to render the subgraph.</div>;
  }

  return <div aria-label="graph canvas" className="graph-canvas" ref={containerRef} />;
};
