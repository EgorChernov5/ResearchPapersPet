import type {
  ApiErrorResponse,
  DocumentJob,
  DocumentJobListResponse,
  GraphFilters,
  PaperListResponse,
  PaperDetails,
  ResearchGraph,
  ResearchJob,
  ResearchProject,
  ResearchQuestionsResponse,
  ResearchSetupInput,
} from "@/api/structures";

export class ResearchApi {
  private readonly baseUrl: string;

  constructor(baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private async request<ResponseBody>(path: string, init?: RequestInit): Promise<ResponseBody> {
    const response = await fetch(`${this.baseUrl}${path}`, init);
    if (!response.ok) {
      let message = `Request failed with status ${response.status}`;
      try {
        const payload = (await response.json()) as ApiErrorResponse;
        if (typeof payload.detail === "string") {
          message = payload.detail;
        } else if (Array.isArray(payload.detail)) {
          message = payload.detail.map((item) => item.msg).join("; ");
        }
      } catch {
        message = response.statusText || message;
      }
      throw new Error(message);
    }
    return (await response.json()) as ResponseBody;
  }

  async createProject(input: ResearchSetupInput): Promise<ResearchProject> {
    return this.request<ResearchProject>("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: input.name, config: input.config }),
    });
  }

  async addQuestions(projectId: string, questions: string[]): Promise<ResearchQuestionsResponse> {
    return this.request<ResearchQuestionsResponse>(`/projects/${projectId}/questions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ questions }),
    });
  }

  async uploadRelatedWork(projectId: string, file: File): Promise<void> {
    const body = new FormData();
    body.append("file", file);
    await this.request(`/projects/${projectId}/related-work`, {
      method: "POST",
      body,
    });
  }

  async startResearch(projectId: string): Promise<ResearchJob> {
    return this.request<ResearchJob>(`/projects/${projectId}/research`, { method: "POST" });
  }

  async getResearchStatus(jobId: string): Promise<ResearchJob> {
    return this.request<ResearchJob>(`/research/${jobId}`);
  }

  async getRanking(projectId: string, filters: GraphFilters = {}): Promise<PaperListResponse> {
    const parameters = new URLSearchParams({ sort_by: "final_score", descending: "true" });
    if (filters.min_topic_score !== undefined) {
      parameters.set("min_topic_score", String(filters.min_topic_score));
    }
    if (filters.min_final_score !== undefined) {
      parameters.set("min_final_score", String(filters.min_final_score));
    }
    if (filters.min_year !== undefined) {
      parameters.set("min_year", String(filters.min_year));
    }
    if (filters.min_citations !== undefined) {
      parameters.set("min_citations", String(filters.min_citations));
    }
    if (filters.max_depth !== undefined) {
      parameters.set("max_depth", String(filters.max_depth));
    }
    if (filters.category) {
      parameters.set("category", filters.category);
    }
    if (filters.is_seed !== undefined) {
      parameters.set("is_seed", String(filters.is_seed));
    }
    return this.request<PaperListResponse>(`/projects/${projectId}/ranking?${parameters}`);
  }

  async getGraph(projectId: string, filters: GraphFilters = {}): Promise<ResearchGraph> {
    const parameters = new URLSearchParams();
    if (filters.min_topic_score !== undefined) {
      parameters.set("min_topic_score", String(filters.min_topic_score));
    }
    if (filters.min_final_score !== undefined) {
      parameters.set("min_final_score", String(filters.min_final_score));
    }
    if (filters.min_year !== undefined) {
      parameters.set("min_year", String(filters.min_year));
    }
    if (filters.min_citations !== undefined) {
      parameters.set("min_citations", String(filters.min_citations));
    }
    if (filters.max_depth !== undefined) {
      parameters.set("max_depth", String(filters.max_depth));
    }
    if (filters.category) {
      parameters.set("category", filters.category);
    }
    if (filters.is_seed !== undefined) {
      parameters.set("is_seed", String(filters.is_seed));
    }
    const query = parameters.size ? `?${parameters}` : "";
    return this.request<ResearchGraph>(`/projects/${projectId}/graph${query}`);
  }

  async getPaperDetails(projectId: string, paperId: string): Promise<PaperDetails> {
    return this.request<PaperDetails>(`/projects/${projectId}/papers/${paperId}`);
  }

  async getProjectDocuments(projectId: string): Promise<DocumentJobListResponse> {
    return this.request<DocumentJobListResponse>(`/projects/${projectId}/documents`);
  }

  async uploadPaperDocument(
    projectId: string,
    paperId: string,
    file: File,
  ): Promise<DocumentJob> {
    const body = new FormData();
    body.append("file", file);
    return this.request<DocumentJob>(`/projects/${projectId}/papers/${paperId}/document`, {
      method: "POST",
      body,
    });
  }
}
