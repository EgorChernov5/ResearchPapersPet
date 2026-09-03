import type {
  ResearchConfigRequest,
  ResearchGraph,
  ResearchJobStatus,
} from "@/api/structures";

export const DEFAULT_RESEARCH_CONFIG: ResearchConfigRequest = {
  max_depth: 2,
  max_papers: 300,
  top_k_expansion: 20,
};

export const JOB_STATUS_LABELS: Record<ResearchJobStatus, string> = {
  PENDING: "Waiting for worker",
  RESOLVING_SEEDS: "Resolving seed papers",
  DISCOVERING: "Exploring citations",
  EMBEDDING: "Building embeddings",
  SCORING: "Calculating relevance",
  GRAPH_ANALYSIS: "Analyzing citation graph",
  COMPLETED: "Research complete",
  FAILED: "Research failed",
};

export const POLL_INTERVAL_MS = 1500;

export const EMPTY_RESEARCH_GRAPH: ResearchGraph = {
  nodes: [],
  edges: [],
};
