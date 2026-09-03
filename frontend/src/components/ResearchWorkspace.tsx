"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ResearchApi } from "@/api/research-api";
import type {
  GraphFilters as GraphFilterValues,
  Paper,
  PaperDetails,
  ResearchGraph,
  ResearchJob,
  ResearchProject,
  ResearchSetupInput,
} from "@/api/structures";
import { GraphExplorer } from "@/components/GraphExplorer/GraphExplorer";
import { GraphFilters } from "@/components/GraphFilters/GraphFilters";
import { PaperPanel } from "@/components/PaperPanel/PaperPanel";
import { PapersTable } from "@/components/PapersTable/PapersTable";
import { ResearchForm } from "@/components/ResearchForm/ResearchForm";
import { ResearchProgress } from "@/components/ResearchProgress/ResearchProgress";
import { EMPTY_RESEARCH_GRAPH, POLL_INTERVAL_MS } from "@/constants";

export function ResearchWorkspace() {
  const api = useMemo(() => new ResearchApi(), []);
  const [project, setProject] = useState<ResearchProject | null>(null);
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [graph, setGraph] = useState<ResearchGraph | null>(null);
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [paperDetails, setPaperDetails] = useState<PaperDetails | null>(null);
  const selectedPaperIdRef = useRef<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingRanking, setIsLoadingRanking] = useState(false);
  const [isLoadingGraph, setIsLoadingGraph] = useState(false);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isResearchActive =
    job !== null && job.status !== "COMPLETED" && job.status !== "FAILED";

  async function handleResearchStart(input: ResearchSetupInput) {
    setIsSubmitting(true);
    setError(null);
    setPapers([]);
    setGraph(null);
    setSelectedPaperId(null);
    selectedPaperIdRef.current = null;
    setPaperDetails(null);
    setJob(null);
    setProject(null);

    try {
      // Persist setup in the same order required by the backend workflow.
      setStatusMessage("Создаём research project…");
      const createdProject = await api.createProject(input);
      setProject(createdProject);

      setStatusMessage("Сохраняем research questions…");
      const createdQuestions = await api.addQuestions(createdProject.id, input.questions);
      setProject({ ...createdProject, questions: createdQuestions.questions });

      setStatusMessage("Загружаем Related Work…");
      await api.uploadRelatedWork(createdProject.id, input.file);

      setStatusMessage("Ставим research job в очередь…");
      const createdJob = await api.startResearch(createdProject.id);
      setJob(createdJob);
      setStatusMessage(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось запустить research.");
      setStatusMessage(null);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleReset() {
    setProject(null);
    setJob(null);
    setPapers([]);
    setGraph(null);
    setSelectedPaperId(null);
    selectedPaperIdRef.current = null;
    setPaperDetails(null);
    setError(null);
    setStatusMessage(null);
  }

  async function handleGraphFilters(filters: GraphFilterValues) {
    if (project === null) {
      return;
    }

    // Keep the graph and table synchronized through the same read-time filters.
    setIsLoadingGraph(true);
    setIsLoadingRanking(true);
    setError(null);
    try {
      const [filteredGraph, ranking] = await Promise.all([
        api.getGraph(project.id, filters),
        api.getRanking(project.id, filters),
      ]);
      setGraph(filteredGraph);
      setPapers(ranking.papers);
      if (
        selectedPaperId !== null &&
        !filteredGraph.nodes.some((paper) => paper.paper_id === selectedPaperId)
      ) {
        setSelectedPaperId(null);
        selectedPaperIdRef.current = null;
        setPaperDetails(null);
      }
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : "Не удалось применить filters.",
      );
    } finally {
      setIsLoadingGraph(false);
      setIsLoadingRanking(false);
    }
  }

  const handlePaperSelect = useCallback(
    (paperId: string | null) => {
      setSelectedPaperId(paperId);
      selectedPaperIdRef.current = paperId;
      setPaperDetails(null);
      if (paperId === null || project === null) {
        setIsLoadingDetails(false);
        return;
      }

      // Resolve project-specific paper scores only after an explicit selection.
      setIsLoadingDetails(true);
      void api
        .getPaperDetails(project.id, paperId)
        .then((details) => {
          if (selectedPaperIdRef.current === paperId) {
            setPaperDetails(details);
          }
        })
        .catch((caughtError: unknown) => {
          if (selectedPaperIdRef.current === paperId) {
            setError(
              caughtError instanceof Error
                ? caughtError.message
                : "Не удалось загрузить paper details.",
            );
          }
        })
        .finally(() => {
          if (selectedPaperIdRef.current === paperId) {
            setIsLoadingDetails(false);
          }
        });
    },
    [api, project],
  );

  useEffect(() => {
    if (!job || job.status === "COMPLETED" || job.status === "FAILED") {
      return;
    }

    // Poll only observable job state; filters and ranking never rerun the pipeline.
    const timer = window.setInterval(() => {
      void api
        .getResearchStatus(job.id)
        .then(async (updatedJob) => {
          setJob(updatedJob);
          if (updatedJob.status === "FAILED") {
            setError(updatedJob.error_message ?? "Research pipeline завершился с ошибкой.");
          } else {
            setError(null);
          }
          if (updatedJob.status === "COMPLETED" && project !== null) {
            setIsLoadingRanking(true);
            setIsLoadingGraph(true);
            try {
              const [ranking, completedGraph] = await Promise.all([
                api.getRanking(project.id),
                api.getGraph(project.id),
              ]);
              setPapers(ranking.papers);
              setGraph(completedGraph);
            } catch (caughtError) {
              setError(
                caughtError instanceof Error
                  ? caughtError.message
                  : "Не удалось загрузить ranking.",
              );
            } finally {
              setIsLoadingRanking(false);
              setIsLoadingGraph(false);
            }
          }
        })
        .catch((caughtError: unknown) => {
          setError(
            caughtError instanceof Error
              ? caughtError.message
              : "Не удалось обновить progress.",
          );
        });
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, [api, job, project]);

  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="Research Graph home">
          <span className="brand-mark" aria-hidden="true">
            RG
          </span>
          <span>
            <strong>Research Graph</strong>
            <small>Scientific discovery workspace</small>
          </span>
        </a>
        <div className="system-state">
          <span /> API + Worker
        </div>
      </header>

      <section className="hero" id="top">
        <div>
          <span className="hero-kicker">Evidence starts with a better map</span>
          <h1>
            Найдите статьи,
            <br />
            <em>которые связывают идеи.</em>
          </h1>
        </div>
        <p>
          Исследуйте citation neighborhood исходных работ и ранжируйте найденные papers по
          semantic, impact и graph relevance.
        </p>
      </section>

      <div className="workspace-grid">
        <ResearchForm
          disabled={isSubmitting || isResearchActive}
          statusMessage={statusMessage}
          onSubmit={handleResearchStart}
        />
        <div className="progress-column">
          <ResearchProgress job={job} />
          {project && (
            <div className="project-receipt">
              <span>Active project</span>
              <strong>{project.name}</strong>
              <code>{project.id}</code>
              {!isResearchActive && !isLoadingRanking && (
                <button type="button" onClick={handleReset}>
                  Новое исследование
                </button>
              )}
            </div>
          )}
          {error && <div className="global-error">{error}</div>}
        </div>
      </div>

      {job?.status === "COMPLETED" && project && (
        <section className="graph-section">
          <div className="results-heading graph-section-heading">
            <div className="section-heading compact-heading">
              <span className="eyebrow">03 · Citation graph</span>
              <h2>Карта научного контекста</h2>
            </div>
            <span className="result-count">Hover to trace · Click for details</span>
          </div>
          <div className="graph-workspace">
            <GraphFilters loading={isLoadingGraph} onApply={handleGraphFilters} />
            <GraphExplorer
              graph={graph ?? EMPTY_RESEARCH_GRAPH}
              loading={isLoadingGraph}
              selectedPaperId={selectedPaperId}
              onSelectPaper={handlePaperSelect}
            />
            <PaperPanel
              details={paperDetails}
              questions={project.questions}
              loading={isLoadingDetails}
              onClose={() => handlePaperSelect(null)}
            />
          </div>
        </section>
      )}

      <PapersTable
        papers={papers}
        loading={isLoadingRanking}
        onSelectPaper={handlePaperSelect}
      />

      <footer>
        <span>Research Graph MVP</span>
        <span>Semantic Scholar · NetworkX · SPECTER</span>
      </footer>
    </main>
  );
}
