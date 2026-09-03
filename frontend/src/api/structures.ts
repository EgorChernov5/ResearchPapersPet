export interface ResearchConfigRequest {
  max_depth: number;
  max_papers: number;
  top_k_expansion: number;
  min_year?: number;
}

export interface ResearchSetupInput {
  name: string;
  questions: string[];
  file: File;
  config: ResearchConfigRequest;
}

export interface ResearchQuestion {
  id: string;
  project_id: string;
  text: string;
}

export interface ResearchQuestionsResponse {
  questions: ResearchQuestion[];
}

export interface ResearchProject {
  id: string;
  name: string;
  config: ResearchConfigRequest;
  questions: ResearchQuestion[];
}

export type ResearchJobStatus =
  | "PENDING"
  | "RESOLVING_SEEDS"
  | "DISCOVERING"
  | "EMBEDDING"
  | "SCORING"
  | "GRAPH_ANALYSIS"
  | "COMPLETED"
  | "FAILED";

export interface ResearchJob {
  id: string;
  project_id: string;
  status: ResearchJobStatus;
  progress: number;
  papers_discovered: number;
  papers_processed: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Paper {
  paper_id: string;
  semantic_scholar_id: string | null;
  title: string;
  abstract: string | null;
  year: number | null;
  citation_count: number | null;
  influential_citation_count: number | null;
  reference_count: number | null;
  authors: string[];
  categories: string[];
  pdf_url: string | null;
  is_seed: boolean;
  depth: number | null;
  query_similarity: number | null;
  seed_similarity: number | null;
  topic_score: number | null;
  citation_score: number | null;
  recency_score: number | null;
  impact_score: number | null;
  distance_score: number | null;
  connectivity_score: number | null;
  pagerank_score: number | null;
  graph_score: number | null;
  final_score: number | null;
}

export interface PaperListResponse {
  count: number;
  papers: Paper[];
}

export interface GraphFilters {
  min_topic_score?: number;
  min_final_score?: number;
  min_year?: number;
  min_citations?: number;
  max_depth?: number;
  category?: string;
  is_seed?: boolean;
}

export interface GraphEdge {
  source_paper_id: string;
  target_paper_id: string;
}

export interface ResearchGraph {
  nodes: Paper[];
  edges: GraphEdge[];
}

export interface PaperQuestionScore {
  project_id: string;
  paper_id: string;
  question_id: string;
  query_similarity: number | null;
  topic_score: number | null;
}

export interface PaperDetails {
  paper: Paper;
  question_scores: PaperQuestionScore[];
}

export interface ApiErrorResponse {
  detail?: string | Array<{ msg: string }>;
}
