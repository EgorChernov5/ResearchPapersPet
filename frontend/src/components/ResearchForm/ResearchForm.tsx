"use client";

import { useState, type FormEvent } from "react";

import type { ResearchSetupInput } from "@/api/structures";
import { DEFAULT_RESEARCH_CONFIG } from "@/constants";

interface ResearchFormProps {
  disabled: boolean;
  statusMessage: string | null;
  onSubmit: (input: ResearchSetupInput) => Promise<void>;
}

export function ResearchForm({ disabled, statusMessage, onSubmit }: ResearchFormProps) {
  const [name, setName] = useState("");
  const [questionsText, setQuestionsText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [maxDepth, setMaxDepth] = useState(String(DEFAULT_RESEARCH_CONFIG.max_depth));
  const [maxPapers, setMaxPapers] = useState(String(DEFAULT_RESEARCH_CONFIG.max_papers));
  const [topKExpansion, setTopKExpansion] = useState(
    String(DEFAULT_RESEARCH_CONFIG.top_k_expansion),
  );
  const [minYear, setMinYear] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    // Normalize one research question per non-empty line.
    const questions = questionsText
      .split("\n")
      .map((question) => question.trim())
      .filter(Boolean);
    if (questions.length === 0) {
      setFormError("Добавьте хотя бы один research question.");
      return;
    }
    if (file === null) {
      setFormError("Выберите Related Work в формате XLSX или CSV.");
      return;
    }

    // Send the validated setup as one frontend workflow input.
    await onSubmit({
      name: name.trim(),
      questions,
      file,
      config: {
        max_depth: Number(maxDepth),
        max_papers: Number(maxPapers),
        top_k_expansion: Number(topKExpansion),
        ...(minYear.trim() ? { min_year: Number(minYear) } : {}),
      },
    });
  }

  return (
    <form className="research-form" onSubmit={handleSubmit}>
      <div className="section-heading">
        <span className="eyebrow">01 · Research setup</span>
        <h2>Сформулируйте область поиска</h2>
        <p>
          Загрузите исходные статьи и задайте вопросы. Система расширит citation neighborhood и
          рассчитает итоговый ranking.
        </p>
      </div>

      <label className="field field-wide">
        <span>Название проекта</span>
        <input
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Например, Graph-aware scientific retrieval"
          maxLength={255}
          required
          disabled={disabled}
        />
      </label>

      <label className="field field-wide">
        <span>Research questions</span>
        <textarea
          value={questionsText}
          onChange={(event) => setQuestionsText(event.target.value)}
          placeholder={"Один вопрос на строку\nHow does graph structure improve paper retrieval?"}
          rows={5}
          required
          disabled={disabled}
        />
        <small>Каждая непустая строка станет отдельным вопросом.</small>
      </label>

      <label className="upload-field field-wide">
        <span className="upload-icon" aria-hidden="true">
          ↗
        </span>
        <span>
          <strong>{file?.name ?? "Related Work file"}</strong>
          <small>{file ? `${(file.size / 1024).toFixed(1)} KB` : "XLSX или CSV · до 10 MB"}</small>
        </span>
        <input
          type="file"
          accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          disabled={disabled}
        />
      </label>

      <details className="advanced field-wide">
        <summary>Параметры исследования</summary>
        <div className="config-grid">
          <label className="field">
            <span>Глубина графа</span>
            <input
              type="number"
              min="1"
              value={maxDepth}
              onChange={(event) => setMaxDepth(event.target.value)}
              required
              disabled={disabled}
            />
          </label>
          <label className="field">
            <span>Максимум статей</span>
            <input
              type="number"
              min="1"
              value={maxPapers}
              onChange={(event) => setMaxPapers(event.target.value)}
              required
              disabled={disabled}
            />
          </label>
          <label className="field">
            <span>Top-K expansion</span>
            <input
              type="number"
              min="1"
              value={topKExpansion}
              onChange={(event) => setTopKExpansion(event.target.value)}
              required
              disabled={disabled}
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
              disabled={disabled}
            />
          </label>
        </div>
      </details>

      {formError && <p className="form-message error-message">{formError}</p>}
      {statusMessage && <p className="form-message pending-message">{statusMessage}</p>}

      <button className="primary-button" type="submit" disabled={disabled}>
        <span>{disabled ? "Research запущен" : "Запустить исследование"}</span>
        <span aria-hidden="true">→</span>
      </button>
    </form>
  );
}
