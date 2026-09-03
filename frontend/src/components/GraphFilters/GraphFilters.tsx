"use client";

import { useState, type FormEvent } from "react";

import type { GraphFilters as GraphFilterValues } from "@/api/structures";

interface GraphFiltersProps {
  loading: boolean;
  onApply: (filters: GraphFilterValues) => Promise<void>;
}

export function GraphFilters({ loading, onApply }: GraphFiltersProps) {
  const [minTopicScore, setMinTopicScore] = useState("");
  const [minFinalScore, setMinFinalScore] = useState("");
  const [minYear, setMinYear] = useState("");
  const [minCitations, setMinCitations] = useState("");
  const [maxDepth, setMaxDepth] = useState("");
  const [category, setCategory] = useState("");
  const [seedStatus, setSeedStatus] = useState("");

  async function handleApply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    // Convert only populated controls into read-time API filters.
    await onApply({
      ...(minTopicScore ? { min_topic_score: Number(minTopicScore) } : {}),
      ...(minFinalScore ? { min_final_score: Number(minFinalScore) } : {}),
      ...(minYear ? { min_year: Number(minYear) } : {}),
      ...(minCitations ? { min_citations: Number(minCitations) } : {}),
      ...(maxDepth ? { max_depth: Number(maxDepth) } : {}),
      ...(category.trim() ? { category: category.trim() } : {}),
      ...(seedStatus ? { is_seed: seedStatus === "seed" } : {}),
    });
  }

  async function handleReset() {
    setMinTopicScore("");
    setMinFinalScore("");
    setMinYear("");
    setMinCitations("");
    setMaxDepth("");
    setCategory("");
    setSeedStatus("");
    await onApply({});
  }

  return (
    <form className="graph-filters" onSubmit={handleApply}>
      <div className="graph-panel-heading">
        <span className="eyebrow">Filters</span>
        <h3>Сузить граф</h3>
        <p>Фильтры читают persisted results и не запускают research повторно.</p>
      </div>

      <label className="field">
        <span>Min topic score</span>
        <input
          type="number"
          min="0"
          max="1"
          step="0.05"
          value={minTopicScore}
          onChange={(event) => setMinTopicScore(event.target.value)}
          placeholder="0.00"
          disabled={loading}
        />
      </label>
      <label className="field">
        <span>Min final score</span>
        <input
          type="number"
          min="0"
          max="1"
          step="0.05"
          value={minFinalScore}
          onChange={(event) => setMinFinalScore(event.target.value)}
          placeholder="0.00"
          disabled={loading}
        />
      </label>
      <label className="field">
        <span>Минимальный год</span>
        <input
          type="number"
          min="1000"
          value={minYear}
          onChange={(event) => setMinYear(event.target.value)}
          placeholder="Без ограничения"
          disabled={loading}
        />
      </label>
      <label className="field">
        <span>Min citations</span>
        <input
          type="number"
          min="0"
          value={minCitations}
          onChange={(event) => setMinCitations(event.target.value)}
          placeholder="0"
          disabled={loading}
        />
      </label>
      <label className="field">
        <span>Max depth</span>
        <input
          type="number"
          min="0"
          value={maxDepth}
          onChange={(event) => setMaxDepth(event.target.value)}
          placeholder="Любая"
          disabled={loading}
        />
      </label>
      <label className="field">
        <span>Category</span>
        <input
          type="text"
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          placeholder="Computer Science"
          disabled={loading}
        />
      </label>
      <label className="field">
        <span>Paper origin</span>
        <select
          value={seedStatus}
          onChange={(event) => setSeedStatus(event.target.value)}
          disabled={loading}
        >
          <option value="">All papers</option>
          <option value="seed">Seed only</option>
          <option value="discovered">Discovered only</option>
        </select>
      </label>

      <div className="filter-actions">
        <button className="filter-apply" type="submit" disabled={loading}>
          {loading ? "Loading…" : "Применить"}
        </button>
        <button className="filter-reset" type="button" onClick={handleReset} disabled={loading}>
          Сбросить
        </button>
      </div>
    </form>
  );
}
