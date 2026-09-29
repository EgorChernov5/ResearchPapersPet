# Architecture decisions

## ADR-001: Две стадии semantic scoring

Статус: принято.

Research pipeline использует semantic relevance дважды, но с разной областью ответственности.

Preliminary scoring выполняется во время citation traversal до появления project graph. Для каждой
пары `candidate × research question` он использует только similarity кандидата к вопросу и seed
papers. Per-question shortlists поступают в balanced selector, который формирует ограниченный
frontier. Citation count, recency, PageRank и другие graph/impact signals здесь недоступны и не
должны влиять на отбор.

Final semantic scoring выполняется после сохранения выбранного induced graph. Он сохраняет
question-level и агрегированные project scores для всех выбранных papers, после чего существующие
impact, graph и final rankers рассчитывают публичный ranking.

Обе стадии используют один versioned global `PaperEmbedding` cache в PostgreSQL/pgvector. Seeds
сохраняются глобально и получают embeddings до первого provider expansion; кандидаты получают их
перед preliminary selection. Project membership, citation edges и discovery depth сохраняются
только после завершения bounded traversal. Поэтому повторный research job переиспользует global
papers и embeddings, а repository upsert-контракты не создают duplicates.

Такое разделение сохраняет прежний ranking API, но не позволяет final graph signals циклически
влиять на состав graph, который необходим для их собственного расчёта.
