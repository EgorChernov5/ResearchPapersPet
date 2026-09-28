import { afterEach, describe, expect, it, vi } from "vitest";

import { ResearchApi } from "../src/api/research-api";
import type { ResearchSetupInput } from "../src/api/structures";

describe("ResearchApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates a project through the configured API origin", async () => {
    const project = {
      id: "project-1",
      name: "Graph retrieval",
      config: {
        max_depth: 1,
        max_papers: 50,
        top_k_expansion: 10,
        expand_references_topic_threshold: 0.7,
        pdf_top_n: 6,
        allow_manual_pdf_upload: true,
      },
      questions: [],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(project), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const input: ResearchSetupInput = {
      name: project.name,
      questions: ["How does graph retrieval work?"],
      file: {} as File,
      config: project.config,
    };

    const result = await new ResearchApi("http://api.test/").createProject(input);

    expect(result).toEqual(project);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/projects",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: input.name, config: input.config }),
      }),
    );
  });

  it("surfaces FastAPI detail messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Research project was not found" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(new ResearchApi("http://api.test").getResearchStatus("missing")).rejects.toThrow(
      "Research project was not found",
    );
  });

  it("serializes graph filters without starting research", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ nodes: [], edges: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await new ResearchApi("http://api.test").getGraph("project-1", {
      min_final_score: 0.7,
      max_depth: 1,
      category: "Machine Learning",
      is_seed: false,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/projects/project-1/graph?" +
        "min_final_score=0.7&max_depth=1&category=Machine+Learning&is_seed=false",
      undefined,
    );
  });
});
