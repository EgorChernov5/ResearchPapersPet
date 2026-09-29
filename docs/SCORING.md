# Scoring научных публикаций

Документ описывает метрики, формулы и стандартные веса, применяемые к каждой статье
исследовательского проекта. Preliminary ranking реализован отдельно в
`backend/app/research/preliminary_scoring.py`; итоговый pipeline использует
`semantic_ranking.py`, `impact_ranking.py`, `graph_analysis.py` и `final_scoring.py`.

## Общая схема

```text
title + abstract + research questions + seed papers
                         │
                         ├─ query_similarity ─┐
                         └─ seed_similarity ──┴─ topic_score

citation_count ──────────── citation_score ──┐
publication year ─────────── recency_score ──┼─ impact_score
directed citation graph ──── pagerank_score ─┘

distance from seeds ──────── distance_score ─────┐
incident citation edges ──── connectivity_score ─┴─ graph_score

topic_score + impact_score + graph_score ────────── final_score
```

Статья и каждый вопрос кодируются одной Sentence Transformers-моделью. Для статьи с abstract
входной текст имеет вид `{title} [SEP] {abstract}`. При отсутствующем или пустом abstract в
encoder передаётся ровно `{title}`, без separator и пустого хвоста.

## Preliminary и final scoring

Preliminary topic score применяется во время discovery до включения статьи в persisted graph.
Для каждой пары `candidate × question` он использует только `query_similarity` и максимальную
`seed_similarity` с текущими весами `0.70/0.30`:

```text
preliminary_topic_score(candidate, question) =
    0.70 × query_similarity(candidate, question)
  + 0.30 × seed_similarity(candidate)
```

Если один компонент отсутствует, применяется общая missing-value policy с перенормировкой
доступных весов. Citations, recency, PageRank и прочие graph/impact signals в preliminary score
не входят. Каждый вопрос формирует независимый shortlist; сбалансированное объединение этих
shortlists определяет общий набор кандидатов для frontier и позднее используется при выборе PDF.

Selector выполняет один первый проход по вопросам в сохранённом порядке. Для каждого вопроса он
берёт кандидата с максимальным `preliminary_topic_score`, которого ещё нет в результате. Если
лидер уже выбран другим вопросом, используется следующий уникальный кандидат его shortlist. Так
при `top_k_expansion >= question_count` каждый непустой вопрос получает представителя, если в его
shortlist существует отдельный доступный paper.

После первого прохода свободные места общего `top_k_expansion` заполняются кандидатами всех
shortlists по убыванию `preliminary_topic_score`. Paper, встретившийся у нескольких вопросов,
добавляется только один раз. Для одинаковых scores используется возрастание canonical paper UUID;
`None` следует после числовых scores. Поэтому выбор детерминирован для одинакового входа и никогда
не превышает глобальный лимит уровня.

Versioned paper embeddings являются глобальным cache: scorer сначала читает совместимые
`model_name + model_version + dimensions` vectors из PostgreSQL/pgvector и создаёт только
отсутствующие. Embeddings вопросов вычисляются в том же model space для конкретного запуска.
Кандидаты сортируются по `preliminary_topic_score` по убыванию, затем по canonical UUID;
отброшенные кандидаты не получают project-specific score records.

Final score рассчитывается после формирования project graph. Он объединяет topic, impact и graph
компоненты и используется для итогового ranking, но не для предварительного отбора frontier.

## Место preliminary score в traversal

Обход выполняется breadth-first по целым уровням. Seeds получают depth `0` и раскрываются в обе
стороны. Для каждого следующего уровня кандидаты всех frontier papers сначала объединяются и
дедуплицируются, затем один общий preliminary scoring и balanced selection формируют следующий
frontier. Поэтому `top_k_expansion` ограничивает уровень целиком, а не отдельный узел или
направление provider request.

Лучший preliminary score выбранной paper среди research questions сохраняется в памяти обхода и
решает только одно: запрашивать ли её references на следующем уровне. Citations запрашиваются
независимо от score. Preliminary score не подмешивается в final score и не меняет формулы impact,
PageRank или graph proximity. После завершения обхода project graph получает только выбранные
papers и induced citation edges, у которых выбраны оба конца.

## Стандартные веса

| Группа | Компонент | Вес |
|---|---|---:|
| Topic | Query similarity | 0.70 |
| Topic | Seed similarity | 0.30 |
| Impact | Citation score | 0.50 |
| Impact | Recency score | 0.20 |
| Impact | PageRank score | 0.30 |
| Graph | Distance score | 0.60 |
| Graph | Connectivity score | 0.40 |
| Final | Topic score | 0.60 |
| Final | Impact score | 0.25 |
| Final | Graph score | 0.15 |

Веса входят в конфигурацию проекта и проверяются при его создании. Текущий UI показывает
настройки объёма поиска, но не предоставляет редактор scoring weights.

## Семантические метрики

### Query similarity

`query_similarity(p, q)` — cosine similarity embedding статьи `p` и вопроса `q`:

```text
query_similarity(p, q) =
    dot(embedding(p), embedding(q))
    ─────────────────────────────────
    norm(embedding(p)) × norm(embedding(q))
```

Теоретический диапазон — от `-1` до `1`. Значение сохраняется отдельно для каждой пары
`paper × question`. Paper-level `query_similarity` равен максимальному значению среди всех
вопросов проекта.

### Seed similarity

`seed_similarity(p)` — максимальная cosine similarity статьи со всеми доступными seed papers:

```text
seed_similarity(p) = max cosine_similarity(p, seed)
```

Для seed paper значение обычно равно `1`, поскольку набор сравнений включает её собственный
embedding. Если embeddings seeds отсутствуют, значение остаётся `null`.

### Topic score

Для каждой пары `paper × question`:

```text
topic(p, q) =
    0.70 × query_similarity(p, q)
  + 0.30 × seed_similarity(p)
```

Paper-level результат выбирает лучший вопрос:

```text
topic_score(p) = max topic(p, q)
```

Таким образом, высокий результат по одному вопросу достаточен для высокого topic score.
Среднее покрытие всех вопросов в текущей формуле не оценивается.

## Impact-метрики

### Citation score

Число цитирований логарифмируется и нормализуется относительно наиболее цитируемой статьи
текущего проекта:

```text
citation_score(p) =
    ln(1 + citation_count(p))
    ──────────────────────────
    max ln(1 + citation_count)
```

Диапазон — от `0` до `1`. Логарифм уменьшает преимущество публикаций с очень большим числом
цитирований. Метрика является project-relative: её значение зависит от состава проекта.

### Recency score

Актуальность статьи рассчитывается через exponential decay:

```text
age = max(current_year - publication_year, 0)
recency_score = exp(-age / 5)
```

Примеры:

| Возраст статьи | Recency score |
|---:|---:|
| 0 лет | 1.000 |
| 3 года | 0.549 |
| 5 лет | 0.368 |
| 10 лет | 0.135 |

### PageRank score

PageRank рассчитывается на направленном project citation graph, где ребро
`source → target` означает, что source paper цитирует target paper. Raw PageRank нормализуется
по максимальному значению проекта:

```text
pagerank_score(p) = raw_pagerank(p) / max raw_pagerank
```

### Impact score

```text
impact_score =
    0.50 × citation_score
  + 0.20 × recency_score
  + 0.30 × pagerank_score
```

## Graph-метрики

Для анализа используются только статьи текущего проекта и citation edges, оба конца которых
вошли в этот проект.

### In-degree и out-degree

- `in_degree` — число project papers, цитирующих выбранную статью.
- `out_degree` — число project papers, которые цитирует выбранная статья.

### Degree centrality

Доля уникальных соседей статьи в ненаправленной версии project graph:

```text
degree_centrality = unique_neighbors / (paper_count - 1)
```

Метрика вычисляется для анализа, но напрямую не входит в graph или final score.

### Distance from seed и distance score

`distance_from_seed` — длина кратчайшего пути до ближайшей seed paper. При поиске пути граф
рассматривается как ненаправленный, поэтому доступны как references, так и citing papers.

```text
distance_score = 1 / (distance_from_seed + 1)
```

| Расстояние | Distance score |
|---:|---:|
| 0 | 1.000 |
| 1 | 0.500 |
| 2 | 0.333 |
| 3 | 0.250 |

Для disconnected paper расстояние и distance score остаются `null`.

### Connectivity score

```text
connectivity_score =
    in_degree + out_degree
    ───────────────────────
       2 × (paper_count - 1)
```

Диапазон — от `0` до `1`. Учитываются только связи внутри project graph.

### Graph score

```text
graph_score =
    0.60 × distance_score
  + 0.40 × connectivity_score
```

PageRank относится к impact score и напрямую в graph score не входит.

## Final score

```text
final_score =
    0.60 × topic_score
  + 0.25 × impact_score
  + 0.15 × graph_score
```

Ranking сортируется по `final_score` по убыванию. В citation graph более высокий final score
отображается большим размером узла; цвет обозначает seed/discovered status, а не score.

## Отсутствующие значения

Отсутствующая метрика представляется `null`, а не нулём. Её вес исключается, после чего веса
доступных компонентов нормализуются.

Например, без recency score:

```text
impact_score =
    0.50 × citation_score + 0.30 × pagerank_score
    ──────────────────────────────────────────────
                       0.80
```

Тот же принцип применяется при расчёте topic, graph и final score. Если недоступны все
компоненты группы, её агрегированная оценка остаётся `null`.

## Пример расчёта одной статьи

Пусть найдена статья со следующими показателями:

```text
query similarity к лучшему вопросу = 0.82
seed similarity                    = 0.70
citations                          = 120
maximum citations в проекте        = 1000
publication year                   = 2023
current year                       = 2026
normalized PageRank                = 0.65
distance from seed                 = 1
in-degree                          = 3
out-degree                         = 5
paper count                        = 30
```

Расчёт:

```text
topic_score = 0.70 × 0.82 + 0.30 × 0.70
            = 0.784

citation_score = ln(121) / ln(1001)
               ≈ 0.694

recency_score = exp(-3 / 5)
              ≈ 0.549

impact_score = 0.50 × 0.694 + 0.20 × 0.549 + 0.30 × 0.65
             ≈ 0.652

distance_score = 1 / (1 + 1)
               = 0.500

connectivity_score = (3 + 5) / (2 × 29)
                   ≈ 0.138

graph_score = 0.60 × 0.500 + 0.40 × 0.138
            ≈ 0.355

final_score = 0.60 × 0.784 + 0.25 × 0.652 + 0.15 × 0.355
            ≈ 0.687
```

## Где смотреть результаты

| Представление | Доступные значения |
|---|---|
| Ranked table | Topic, Impact, Graph, Final |
| Paper Details | Topic, Impact, Graph, Final и scores по каждому вопросу |
| Citation graph | Final через размер узла и hover-card |
| REST API `/papers` и `/ranking` | Все сохранённые paper-level scores |
| REST API `/papers/{paper_id}` | Paper-level и question-level scores |

В UI доступна краткая раскрываемая легенда. Полные внутренние метрики пока не выводятся
отдельными колонками, но доступны через REST API.
