export type PaperTableColumnKey =
  | "rank"
  | "paper"
  | "year"
  | "citations"
  | "topic"
  | "impact"
  | "graph"
  | "final";

export interface PaperTableColumn {
  key: PaperTableColumnKey;
  label: string;
  definition: string;
  formula: string | null;
  filterType: "text" | "number";
  filterStep: string | null;
}

export interface PaperTableFilter {
  query: string;
  min: string;
  max: string;
}

export const PAPER_TABLE_COLUMNS: PaperTableColumn[] = [
  {
    key: "rank",
    label: "#",
    definition: "Позиция статьи в исходном ranking по Final score.",
    formula: null,
    filterType: "number",
    filterStep: "1",
  },
  {
    key: "paper",
    label: "Paper",
    definition: "Название публикации, её авторы, категории и ссылка на PDF.",
    formula: null,
    filterType: "text",
    filterStep: null,
  },
  {
    key: "year",
    label: "Year",
    definition: "Год публикации статьи.",
    formula: null,
    filterType: "number",
    filterStep: "1",
  },
  {
    key: "citations",
    label: "Citations",
    definition: "Количество цитирований статьи, полученное от провайдера данных.",
    formula: null,
    filterType: "number",
    filterStep: "1",
  },
  {
    key: "topic",
    label: "Topic",
    definition: "Релевантность статьи research questions и seed papers.",
    formula: "0.70 × Query similarity + 0.30 × Seed similarity",
    filterType: "number",
    filterStep: "0.001",
  },
  {
    key: "impact",
    label: "Impact",
    definition: "Научное влияние с учётом citations, актуальности и PageRank.",
    formula: "0.50 × Citation score + 0.20 × Recency score + 0.30 × PageRank score",
    filterType: "number",
    filterStep: "0.001",
  },
  {
    key: "graph",
    label: "Graph",
    definition: "Близость к seed papers и связность внутри citation graph проекта.",
    formula: "0.60 × Distance score + 0.40 × Connectivity score",
    filterType: "number",
    filterStep: "0.001",
  },
  {
    key: "final",
    label: "Final",
    definition: "Итоговая оценка, по которой ранжируются статьи.",
    formula: "0.60 × Topic score + 0.25 × Impact score + 0.15 × Graph score",
    filterType: "number",
    filterStep: "0.001",
  },
];

export const INITIAL_PAPER_TABLE_FILTERS: Record<PaperTableColumnKey, PaperTableFilter> = {
  rank: { query: "", min: "", max: "" },
  paper: { query: "", min: "", max: "" },
  year: { query: "", min: "", max: "" },
  citations: { query: "", min: "", max: "" },
  topic: { query: "", min: "", max: "" },
  impact: { query: "", min: "", max: "" },
  graph: { query: "", min: "", max: "" },
  final: { query: "", min: "", max: "" },
};
