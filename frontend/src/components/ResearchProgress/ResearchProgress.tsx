import type { ResearchJob } from "@/api/structures";
import { JOB_STATUS_LABELS } from "@/constants";

interface ResearchProgressProps {
  job: ResearchJob | null;
}

export function ResearchProgress({ job }: ResearchProgressProps) {
  const progress = job ? Math.min(100, Math.max(0, Math.round(job.progress * 100))) : 0;

  return (
    <section className="progress-card" aria-live="polite">
      <div className="section-heading compact-heading">
        <span className="eyebrow">02 · Background research</span>
        <h2>{job ? JOB_STATUS_LABELS[job.status] : "Ожидает запуска"}</h2>
      </div>

      <div className="progress-value">
        <strong>{progress}</strong>
        <span>%</span>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
      >
        <span style={{ width: `${progress}%` }} />
      </div>

      <dl className="progress-metrics">
        <div>
          <dt>Discovered</dt>
          <dd>{job?.papers_discovered ?? "—"}</dd>
        </div>
        <div>
          <dt>Processed</dt>
          <dd>{job?.papers_processed ?? "—"}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd className={job?.status === "FAILED" ? "status-failed" : "status-live"}>
            {job?.status ?? "IDLE"}
          </dd>
        </div>
      </dl>

      {job?.error_message && <p className="job-error">{job.error_message}</p>}
      {!job && (
        <p className="progress-placeholder">
          После отправки worker будет обновлять этот экран по мере прохождения pipeline.
        </p>
      )}
    </section>
  );
}
