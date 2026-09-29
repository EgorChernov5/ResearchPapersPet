import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { DocumentJob, PaperDetails } from "../src/api/structures";
import { PaperPanel } from "../src/components/PaperPanel/PaperPanel";

const details: PaperDetails = {
  paper: {
    paper_id: "paper-1",
    semantic_scholar_id: "s2-1",
    title: "Manual PDF Paper",
    abstract: null,
    year: 2025,
    citation_count: 1,
    influential_citation_count: null,
    reference_count: null,
    authors: [],
    categories: [],
    pdf_url: null,
    is_seed: true,
    depth: 0,
    query_similarity: null,
    seed_similarity: null,
    topic_score: null,
    citation_score: null,
    recency_score: null,
    impact_score: null,
    distance_score: null,
    connectivity_score: null,
    pagerank_score: null,
    graph_score: null,
    final_score: null,
  },
  question_scores: [],
};

const awaitingDocument: DocumentJob = {
  id: "document-job-1",
  project_id: "project-1",
  paper_id: "paper-1",
  research_job_id: "research-job-1",
  document_id: null,
  source: "ARXIV",
  status: "AWAITING_UPLOAD",
  error_message: "arXiv PDF was not found",
  started_at: null,
  finished_at: null,
  created_at: null,
};

describe("PaperPanel manual PDF fallback", () => {
  it("shows upload only for an allowed AWAITING_UPLOAD target", () => {
    const allowed = renderToStaticMarkup(
      createElement(PaperPanel, {
        details,
        questions: [],
        loading: false,
        documentJob: awaitingDocument,
        allowManualUpload: true,
        onUpload: vi.fn(),
        onClose: vi.fn(),
      }),
    );
    const disabled = renderToStaticMarkup(
      createElement(PaperPanel, {
        details,
        questions: [],
        loading: false,
        documentJob: awaitingDocument,
        allowManualUpload: false,
        onUpload: vi.fn(),
        onClose: vi.fn(),
      }),
    );

    expect(allowed).toContain("Загрузить PDF вручную");
    expect(allowed).toContain('accept="application/pdf,.pdf"');
    expect(disabled).not.toContain("Загрузить PDF вручную");
  });
});
