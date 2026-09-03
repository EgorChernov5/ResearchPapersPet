"use client";

import cytoscape from "cytoscape";
import { useEffect, useRef, useState } from "react";

import type { ResearchGraph } from "@/api/structures";

const DEFAULT_ZOOM_SENSITIVITY = 0.22;

interface GraphExplorerProps {
  graph: ResearchGraph;
  loading: boolean;
  selectedPaperId: string | null;
  onSelectPaper: (paperId: string | null) => void;
}

export function GraphExplorer({
  graph,
  loading,
  selectedPaperId,
  onSelectPaper,
}: GraphExplorerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cytoscapeRef = useRef<cytoscape.Core | null>(null);
  const zoomSensitivityRef = useRef(DEFAULT_ZOOM_SENSITIVITY);
  const [hoveredPaperId, setHoveredPaperId] = useState<string | null>(null);
  const [zoomSensitivity, setZoomSensitivity] = useState(DEFAULT_ZOOM_SENSITIVITY);
  const hoveredPaper = graph.nodes.find((paper) => paper.paper_id === hoveredPaperId) ?? null;

  useEffect(() => {
    if (containerRef.current === null || graph.nodes.length === 0) {
      return;
    }

    // Build a fresh renderer for the current server-filtered subgraph.
    const elements: cytoscape.ElementDefinition[] = [
      ...graph.nodes.map((paper) => ({
        group: "nodes" as const,
        data: {
          id: paper.paper_id,
          label: paper.title,
          finalScore: paper.final_score ?? 0,
          citations: paper.citation_count ?? 0,
        },
        classes: paper.is_seed ? "seed" : "discovered",
      })),
      ...graph.edges.map((edge, index) => ({
        group: "edges" as const,
        data: {
          id: `citation-${index}-${edge.source_paper_id}-${edge.target_paper_id}`,
          source: edge.source_paper_id,
          target: edge.target_paper_id,
        },
      })),
    ];
    const instance = cytoscape({
      container: containerRef.current,
      elements,
      minZoom: 0.18,
      maxZoom: 3.2,
      wheelSensitivity: zoomSensitivityRef.current,
      hideEdgesOnViewport: true,
      style: [
        {
          selector: "node",
          style: {
            width: "mapData(finalScore, 0, 1, 22, 54)",
            height: "mapData(finalScore, 0, 1, 22, 54)",
            "background-color": "#0b6b5e",
            "border-color": "#fffdf7",
            "border-width": 2,
            label: "",
            color: "#17201f",
            "font-size": 10,
            "font-weight": 650,
            "text-wrap": "ellipsis",
            "text-max-width": "180px",
            "text-background-color": "#fffdf7",
            "text-background-opacity": 0,
            "text-background-padding": "5px",
            "overlay-opacity": 0,
            "transition-property": "opacity, border-width, border-color",
            "transition-duration": 140,
          },
        },
        {
          selector: "node.seed",
          style: {
            "background-color": "#e77435",
            "border-color": "#7e3517",
            "border-width": 3,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.2,
            "line-color": "#9aa8a3",
            "target-arrow-color": "#9aa8a3",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.72,
            "curve-style": "bezier",
            opacity: 0.52,
            "overlay-opacity": 0,
          },
        },
        {
          selector: "node.hover-focus, node.selected",
          style: {
            label: "data(label)",
            "text-background-opacity": 0.94,
            "border-color": "#17201f",
            "border-width": 4,
            "z-index": 10,
          },
        },
        {
          selector: ".hover-muted, .selection-muted",
          style: { opacity: 0.14 },
        },
        {
          selector: "edge.hover-focus",
          style: {
            width: 2.4,
            opacity: 0.95,
            "line-color": "#e77435",
            "target-arrow-color": "#e77435",
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        fit: true,
        padding: 54,
        nodeRepulsion: 7600,
        idealEdgeLength: 96,
        edgeElasticity: 110,
        gravity: 0.28,
        numIter: 900,
      },
    });

    instance.on("tap", "node", (event) => onSelectPaper(event.target.id()));
    instance.on("tap", (event) => {
      if (event.target === instance) {
        onSelectPaper(null);
      }
    });
    instance.on("mouseover", "node", (event) => {
      const neighborhood = event.target.closedNeighborhood();
      neighborhood.addClass("hover-focus");
      instance.elements().difference(neighborhood).addClass("hover-muted");
      setHoveredPaperId(event.target.id());
    });
    instance.on("mouseout", "node", () => {
      instance.elements().removeClass("hover-focus hover-muted");
      setHoveredPaperId(null);
    });
    cytoscapeRef.current = instance;

    return () => {
      cytoscapeRef.current = null;
      instance.destroy();
    };
  }, [graph, onSelectPaper]);

  useEffect(() => {
    const instance = cytoscapeRef.current;
    if (instance === null) {
      return;
    }

    // Keep selection independent from transient hover classes.
    instance.elements().removeClass("selected selection-muted");
    if (selectedPaperId === null) {
      return;
    }
    const selected = instance.getElementById(selectedPaperId);
    if (selected.empty()) {
      return;
    }
    const neighborhood = selected.closedNeighborhood();
    selected.addClass("selected");
    instance.elements().difference(neighborhood).addClass("selection-muted");
    instance.fit(neighborhood, 80);
  }, [graph, selectedPaperId]);

  return (
    <div className="graph-explorer">
      <div className="graph-toolbar">
        <div>
          <strong>{graph.nodes.length}</strong> nodes · <strong>{graph.edges.length}</strong> edges
        </div>
        <label className="zoom-sensitivity-control">
          <span>Zoom sensitivity</span>
          <input
            type="range"
            min="0.08"
            max="0.5"
            step="0.01"
            value={zoomSensitivity}
            aria-label="Graph zoom sensitivity"
            onChange={(event) => {
              const value = Number(event.target.value);
              zoomSensitivityRef.current = value;
              setZoomSensitivity(value);
              const instance = cytoscapeRef.current;
              if (instance !== null) {
                const renderer = (
                  instance as cytoscape.Core & {
                    renderer: () => { wheelSensitivity: number };
                  }
                ).renderer();
                renderer.wheelSensitivity = value;
              }
            }}
          />
          <output>{zoomSensitivity.toFixed(2)}</output>
        </label>
        <div>
          <button
            type="button"
            onClick={() => {
              const instance = cytoscapeRef.current;
              if (instance !== null) {
                instance.fit(instance.elements(), 52);
              }
            }}
          >
            Fit
          </button>
          <button
            type="button"
            onClick={() =>
              cytoscapeRef.current
                ?.layout({ name: "cose", animate: true, animationDuration: 320, padding: 52 })
                .run()
            }
          >
            Re-layout
          </button>
        </div>
      </div>

      <div
        className="cytoscape-canvas"
        ref={containerRef}
        role="img"
        aria-label="Interactive citation graph; use the ranked table as a text alternative"
        aria-busy={loading}
      />

      {graph.nodes.length === 0 && !loading && (
        <div className="graph-empty">
          <span>○</span>
          <strong>Нет nodes для выбранных фильтров</strong>
          <p>Сбросьте ограничения или уменьшите score thresholds.</p>
        </div>
      )}
      {loading && <div className="graph-loading">Обновляем graph view…</div>}
      {hoveredPaper && (
        <div className="graph-hover-card">
          <span>{hoveredPaper.is_seed ? "Seed paper" : `Depth ${hoveredPaper.depth ?? "—"}`}</span>
          <strong>{hoveredPaper.title}</strong>
          <small>Final score: {hoveredPaper.final_score?.toFixed(3) ?? "—"}</small>
        </div>
      )}

      <div className="graph-legend">
        <span>
          <i className="legend-seed" /> Seed
        </span>
        <span>
          <i className="legend-paper" /> Discovered
        </span>
        <span>Node size = final score</span>
      </div>
    </div>
  );
}
