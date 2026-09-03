"use client";

import { useMemo, useState } from "react";

import type { Paper } from "@/api/structures";

import {
  INITIAL_PAPER_TABLE_FILTERS,
  PAPER_TABLE_COLUMNS,
  type PaperTableColumnKey,
} from "./columns";

interface PapersTableProps {
  papers: Paper[];
  loading: boolean;
  onSelectPaper: (paperId: string) => void;
}

export function PapersTable({ papers, loading, onSelectPaper }: PapersTableProps) {
  const [visibleColumns, setVisibleColumns] = useState<Set<PaperTableColumnKey>>(
    () => new Set(PAPER_TABLE_COLUMNS.map((column) => column.key)),
  );
  const [filters, setFilters] = useState(INITIAL_PAPER_TABLE_FILTERS);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [exportMessage, setExportMessage] = useState<string | null>(null);

  const filteredRows = useMemo(
    () =>
      papers
        .map((paper, index) => ({ paper, rank: index + 1 }))
        .filter(({ paper, rank }) =>
          PAPER_TABLE_COLUMNS.every((column) => {
            const filter = filters[column.key];
            if (column.filterType === "text") {
              const query = filter.query.trim().toLocaleLowerCase();
              if (query.length === 0) {
                return true;
              }
              return [paper.title, ...paper.authors, ...paper.categories]
                .join(" ")
                .toLocaleLowerCase()
                .includes(query);
            }

            let value: number | null;
            switch (column.key) {
              case "rank":
                value = rank;
                break;
              case "year":
                value = paper.year;
                break;
              case "citations":
                value = paper.citation_count;
                break;
              case "topic":
                value = paper.topic_score;
                break;
              case "impact":
                value = paper.impact_score;
                break;
              case "graph":
                value = paper.graph_score;
                break;
              case "final":
                value = paper.final_score;
                break;
              default:
                value = null;
            }

            const hasMinimum = filter.min !== "";
            const hasMaximum = filter.max !== "";
            if (!hasMinimum && !hasMaximum) {
              return true;
            }
            if (value === null) {
              return false;
            }
            return (
              (!hasMinimum || value >= Number(filter.min)) &&
              (!hasMaximum || value <= Number(filter.max))
            );
          }),
        ),
    [filters, papers],
  );

  const activeFilterCount = PAPER_TABLE_COLUMNS.filter((column) => {
    const filter = filters[column.key];
    return filter.query !== "" || filter.min !== "" || filter.max !== "";
  }).length;

  return (
    <section className="papers-section">
      <div className="results-heading">
        <div className="section-heading compact-heading">
          <span className="eyebrow">04 · Ranked papers</span>
          <h2>Результаты исследования</h2>
        </div>
        <span className="result-count">
          {loading ? "Loading…" : `${filteredRows.length} of ${papers.length} papers`}
        </span>
      </div>

      <details className="score-guide">
        <summary>Как читать scores</summary>
        <div>
          {PAPER_TABLE_COLUMNS.filter((column) => column.formula !== null).map((column) => (
            <p key={column.key}>
              <strong>{column.label}</strong>
              <span>
                {column.definition} Формула: {column.formula}.
              </span>
            </p>
          ))}
        </div>
      </details>

      <div className="table-controls">
        <details className="table-control-panel">
          <summary>Columns · {visibleColumns.size}</summary>
          <div className="column-options">
            {PAPER_TABLE_COLUMNS.map((column) => (
              <label key={column.key}>
                <input
                  type="checkbox"
                  checked={visibleColumns.has(column.key)}
                  disabled={visibleColumns.size === 1 && visibleColumns.has(column.key)}
                  onChange={() => {
                    setVisibleColumns((current) => {
                      const next = new Set(current);
                      if (next.has(column.key)) {
                        next.delete(column.key);
                      } else {
                        next.add(column.key);
                      }
                      return next;
                    });
                  }}
                />
                <span>{column.label}</span>
                <span
                  className="field-help"
                  tabIndex={0}
                  aria-label={`${column.label}: ${column.definition}${
                    column.formula === null ? "" : ` Формула: ${column.formula}.`
                  }`}
                  data-tooltip={`${column.definition}${
                    column.formula === null ? "" : ` Формула: ${column.formula}.`
                  }`}
                >
                  ?
                </span>
              </label>
            ))}
          </div>
        </details>

        <details className="table-control-panel filter-panel">
          <summary>Filters · {activeFilterCount}</summary>
          <div className="filter-grid">
            {PAPER_TABLE_COLUMNS.map((column) => (
              <div className="table-filter" key={column.key}>
                <label htmlFor={`paper-filter-${column.key}`}>
                  <span>{column.label}</span>
                  <span
                    className="field-help"
                    tabIndex={0}
                    aria-label={`${column.label}: ${column.definition}${
                      column.formula === null ? "" : ` Формула: ${column.formula}.`
                    }`}
                    data-tooltip={`${column.definition}${
                      column.formula === null ? "" : ` Формула: ${column.formula}.`
                    }`}
                  >
                    ?
                  </span>
                </label>
                {column.filterType === "text" ? (
                  <input
                    id={`paper-filter-${column.key}`}
                    type="search"
                    value={filters[column.key].query}
                    placeholder="Search"
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        [column.key]: { ...current[column.key], query: event.target.value },
                      }))
                    }
                  />
                ) : (
                  <div className="number-filter">
                    <input
                      id={`paper-filter-${column.key}`}
                      type="number"
                      step={column.filterStep ?? "any"}
                      value={filters[column.key].min}
                      placeholder="Min"
                      aria-label={`${column.label}: minimum`}
                      onChange={(event) =>
                        setFilters((current) => ({
                          ...current,
                          [column.key]: { ...current[column.key], min: event.target.value },
                        }))
                      }
                    />
                    <input
                      type="number"
                      step={column.filterStep ?? "any"}
                      value={filters[column.key].max}
                      placeholder="Max"
                      aria-label={`${column.label}: maximum`}
                      onChange={(event) =>
                        setFilters((current) => ({
                          ...current,
                          [column.key]: { ...current[column.key], max: event.target.value },
                        }))
                      }
                    />
                  </div>
                )}
                <button
                  type="button"
                  disabled={
                    filters[column.key].query === "" &&
                    filters[column.key].min === "" &&
                    filters[column.key].max === ""
                  }
                  onClick={() =>
                    setFilters((current) => ({
                      ...current,
                      [column.key]: { query: "", min: "", max: "" },
                    }))
                  }
                >
                  Clear
                </button>
              </div>
            ))}
          </div>
          <button
            className="clear-all-filters"
            type="button"
            disabled={activeFilterCount === 0}
            onClick={() => setFilters(INITIAL_PAPER_TABLE_FILTERS)}
          >
            Clear all filters
          </button>
        </details>

        <div className="table-export-actions">
          <button
            type="button"
            onClick={() => {
              if (filteredRows.length === 0) {
                setExportMessage("Нет строк для экспорта с текущими фильтрами.");
                return;
              }
              setExportMessage(null);
              setExportDialogOpen(true);
            }}
          >
            Export CSV
          </button>
          {exportMessage !== null && <span role="status">{exportMessage}</span>}
        </div>
      </div>

      <div className="table-shell">
        <table>
          <thead>
            <tr>
              {PAPER_TABLE_COLUMNS.filter((column) => visibleColumns.has(column.key)).map(
                (column) => (
                  <th scope="col" key={column.key}>
                    <span>{column.label}</span>
                    <span
                      className="field-help table-heading-help"
                      tabIndex={0}
                      aria-label={`${column.label}: ${column.definition}${
                        column.formula === null ? "" : ` Формула: ${column.formula}.`
                      }`}
                      data-tooltip={`${column.definition}${
                        column.formula === null ? "" : ` Формула: ${column.formula}.`
                      }`}
                    >
                      ?
                    </span>
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {filteredRows.map(({ paper, rank }) => (
              <tr key={paper.paper_id}>
                {PAPER_TABLE_COLUMNS.map((column) => {
                  if (!visibleColumns.has(column.key)) {
                    return null;
                  }
                  switch (column.key) {
                    case "rank":
                      return (
                        <td className="rank-cell" key={column.key}>
                          {String(rank).padStart(2, "0")}
                        </td>
                      );
                    case "paper":
                      return (
                        <td className="paper-cell" key={column.key}>
                          <div className="paper-title-line">
                            <button type="button" onClick={() => onSelectPaper(paper.paper_id)}>
                              {paper.title}
                            </button>
                            {paper.is_seed && <span className="seed-badge">Seed</span>}
                          </div>
                          <span>
                            {paper.authors.length ? paper.authors.join(", ") : "Unknown authors"}
                          </span>
                          {paper.categories.length > 0 && (
                            <small>{paper.categories.slice(0, 3).join(" · ")}</small>
                          )}
                          {paper.pdf_url && (
                            <a
                              className="table-pdf-link"
                              href={paper.pdf_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              PDF ↗
                            </a>
                          )}
                        </td>
                      );
                    case "year":
                      return <td key={column.key}>{paper.year ?? "—"}</td>;
                    case "citations":
                      return (
                        <td key={column.key}>
                          {paper.citation_count?.toLocaleString("en-US") ?? "—"}
                        </td>
                      );
                    case "topic":
                    case "impact":
                    case "graph":
                    case "final": {
                      const value = {
                        topic: paper.topic_score,
                        impact: paper.impact_score,
                        graph: paper.graph_score,
                        final: paper.final_score,
                      }[column.key];
                      return (
                        <td
                          className={
                            column.key === "final" ? "score-cell final-score" : "score-cell"
                          }
                          key={column.key}
                        >
                          {value === null ? "—" : value.toFixed(3)}
                        </td>
                      );
                    }
                  }
                })}
              </tr>
            ))}
          </tbody>
        </table>

        {!loading && papers.length === 0 && (
          <div className="empty-results">
            <span aria-hidden="true">◇</span>
            <strong>Ranking появится после завершения research job</strong>
            <p>
              Таблица загружается из сохранённых результатов без повторного запуска pipeline.
            </p>
          </div>
        )}
        {!loading && papers.length > 0 && filteredRows.length === 0 && (
          <div className="empty-results filtered-empty-results">
            <span aria-hidden="true">◇</span>
            <strong>По текущим фильтрам статьи не найдены</strong>
            <p>Измените значения или очистите фильтры, чтобы вернуть строки.</p>
          </div>
        )}
      </div>

      {exportDialogOpen && (
        <div className="modal-backdrop" role="presentation">
          <div
            className="export-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="export-dialog-title"
          >
            <span className="eyebrow">CSV export</span>
            <h3 id="export-dialog-title">Выгрузить отфильтрованную таблицу?</h3>
            <p>Будет выгружено строк: {filteredRows.length}.</p>
            <div>
              <button type="button" onClick={() => setExportDialogOpen(false)}>
                Cancel
              </button>
              <button
                className="export-confirm"
                type="button"
                onClick={() => {
                  const columns = PAPER_TABLE_COLUMNS.filter((column) =>
                    visibleColumns.has(column.key),
                  );
                  const csvRows = [
                    columns.map((column) => `"${column.label.replaceAll('"', '""')}"`).join(","),
                    ...filteredRows.map(({ paper, rank }) =>
                      columns
                        .map((column) => {
                          let value: string | number | null;
                          switch (column.key) {
                            case "rank":
                              value = rank;
                              break;
                            case "paper":
                              value = [
                                paper.title,
                                paper.authors.join(", "),
                                paper.categories.join(" · "),
                                paper.pdf_url,
                              ]
                                .filter((item) => item !== null && item !== "")
                                .join(" | ");
                              break;
                            case "year":
                              value = paper.year;
                              break;
                            case "citations":
                              value = paper.citation_count;
                              break;
                            case "topic":
                              value = paper.topic_score;
                              break;
                            case "impact":
                              value = paper.impact_score;
                              break;
                            case "graph":
                              value = paper.graph_score;
                              break;
                            case "final":
                              value = paper.final_score;
                              break;
                          }
                          return `"${String(value ?? "").replaceAll('"', '""')}"`;
                        })
                        .join(","),
                    ),
                  ];
                  const blob = new Blob(["\uFEFF", csvRows.join("\r\n")], {
                    type: "text/csv;charset=utf-8",
                  });
                  const url = URL.createObjectURL(blob);
                  const link = document.createElement("a");
                  link.href = url;
                  link.download = "research-papers.csv";
                  document.body.appendChild(link);
                  link.click();
                  link.remove();
                  URL.revokeObjectURL(url);
                  setExportDialogOpen(false);
                }}
              >
                Export {filteredRows.length} rows
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
