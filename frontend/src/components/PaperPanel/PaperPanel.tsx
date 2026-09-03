import type { PaperDetails, ResearchQuestion } from "@/api/structures";

interface PaperPanelProps {
  details: PaperDetails | null;
  questions: ResearchQuestion[];
  loading: boolean;
  onClose: () => void;
}

function ScoreMetric({
  label,
  value,
  description,
}: {
  label: string;
  value: number | null;
  description: string;
}) {
  return (
    <div className="panel-score">
      <span title={description}>{label}</span>
      <strong>{value?.toFixed(3) ?? "—"}</strong>
      <i>
        <span style={{ width: `${Math.max(0, Math.min(1, value ?? 0)) * 100}%` }} />
      </i>
    </div>
  );
}

export function PaperPanel({ details, questions, loading, onClose }: PaperPanelProps) {
  const questionsById = new Map(questions.map((question) => [question.id, question.text]));

  if (loading) {
    return <aside className="paper-panel paper-panel-loading">Загружаем paper details…</aside>;
  }

  if (details === null) {
    return (
      <aside className="paper-panel paper-panel-empty">
        <span aria-hidden="true">↖</span>
        <strong>Выберите paper node</strong>
        <p>Клик откроет metadata, component scores и relevance по каждому research question.</p>
      </aside>
    );
  }

  const paper = details.paper;
  return (
    <aside className="paper-panel" aria-label="Paper details">
      <button className="panel-close" type="button" onClick={onClose} aria-label="Close details">
        ×
      </button>
      <span className="eyebrow">Paper details</span>
      <div className="panel-title-row">
        <h3>{paper.title}</h3>
        {paper.is_seed && <span className="seed-badge">Seed</span>}
      </div>
      <p className="panel-authors">
        {paper.authors.length ? paper.authors.join(", ") : "Unknown authors"}
      </p>

      <dl className="panel-metadata">
        <div>
          <dt>Year</dt>
          <dd>{paper.year ?? "—"}</dd>
        </div>
        <div>
          <dt>Citations</dt>
          <dd>{paper.citation_count?.toLocaleString("en-US") ?? "—"}</dd>
        </div>
        <div>
          <dt>Depth</dt>
          <dd>{paper.depth ?? "—"}</dd>
        </div>
      </dl>

      {paper.categories.length > 0 && (
        <div className="panel-categories">
          {paper.categories.map((category) => (
            <span key={category}>{category}</span>
          ))}
        </div>
      )}

      <div className="panel-score-grid">
        <ScoreMetric
          label="Topic"
          value={paper.topic_score}
          description="Релевантность вопросам и seed papers"
        />
        <ScoreMetric
          label="Impact"
          value={paper.impact_score}
          description="Citations, актуальность и PageRank"
        />
        <ScoreMetric
          label="Graph"
          value={paper.graph_score}
          description="Близость к seeds и связность citation graph"
        />
        <ScoreMetric
          label="Final"
          value={paper.final_score}
          description="60% Topic, 25% Impact и 15% Graph"
        />
      </div>

      <section className="panel-abstract">
        <h4>Abstract</h4>
        <p>{paper.abstract ?? "Abstract is not available from the provider."}</p>
      </section>

      <section className="question-scores">
        <h4>Research question relevance</h4>
        {details.question_scores.length === 0 ? (
          <p>Question-level scores отсутствуют.</p>
        ) : (
          details.question_scores.map((score) => (
            <article key={score.question_id}>
              <p>{questionsById.get(score.question_id) ?? `Question ${score.question_id}`}</p>
              <div>
                <span>Similarity {score.query_similarity?.toFixed(3) ?? "—"}</span>
                <span>Topic {score.topic_score?.toFixed(3) ?? "—"}</span>
              </div>
            </article>
          ))
        )}
      </section>

      {paper.pdf_url && (
        <a className="panel-pdf-link" href={paper.pdf_url} target="_blank" rel="noreferrer">
          Открыть PDF <span aria-hidden="true">↗</span>
        </a>
      )}
    </aside>
  );
}
