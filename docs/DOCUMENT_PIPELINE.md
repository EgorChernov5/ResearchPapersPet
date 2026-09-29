# Document pipeline

## Ownership и source of truth

`Paper` — глобальный владелец PDF и всех производных версий. Проект не копирует документ: он
создаёт `DocumentProcessingJob`, который фиксирует, какой проект выбрал конкретную статью как PDF
target. Удаление `Paper` каскадно удаляет её документы, parser results, элементы, citation markers,
chunks и project targets. Удаление проекта удаляет только его jobs и не удаляет глобальный PDF,
если статья используется другими проектами.

PostgreSQL является source of truth для metadata, lifecycle, нормализованной структуры и chunks.
Активный `DocumentStorage` является source of truth для бинарных PDF и будущих оригинальных
GROBID TEI. Одновременно выбирается ровно один backend: local volume в development/test или
S3-compatible storage в production. Объект не дублируется между backends. Будущий Qdrant index
остаётся полностью производным и перестраиваемым.

## Object naming и validation boundary

Канонический PDF key имеет вид:

```text
papers/{paper_uuid}/documents/{document_uuid}/{sha256}.pdf
```

Пользовательское filename не входит в key и не влияет на путь. До backend write проверяются
максимальный размер, MIME `application/pdf`, сигнатура `%PDF-` и, если он передан, ожидаемый
SHA-256. Поэтому oversized, non-PDF и повреждённые при передаче объекты не получают успешных
storage metadata. Повторная запись тех же UUID и checksum идемпотентна; другой checksum создаёт
другой immutable object key и позволяет PostgreSQL зарегистрировать новую document version.

Local backend хранит JSON metadata рядом с PDF. S3 backend хранит те же canonical identifiers и
checksum в object metadata. Операции `put`, `get`, `exists`, `delete` и `get_metadata` имеют один
contract, проверяемый общим набором тестов против реального local filesystem и RustFS.

## Research и document boundaries

После final ranking `ResearchJob` выбирает:

1. Все seed papers независимо от `pdf_top_n`.
2. Не более `pdf_top_n` discovered papers.
3. Discovered targets через round-robin по per-question semantic shortlists с дедупликацией и
   стабильным canonical paper ID tie-breaker.

Для каждого target идемпотентно создаётся `(project_id, paper_id, source)` job. Повторный research
run не создаёт duplicate target. `ResearchJob` сразу завершается и не ждёт document worker, поэтому
`AWAITING_UPLOAD` не блокирует metadata/ranking workflow.

После terminal success ResearchJob тот же worker запускает независимый automatic document pass.
Canonical arXiv identifier читается из `external_identifiers`; URL или пользовательский filename не
используются как object key. Клиент следует redirect, использует bounded timeout/retry, корректный
User-Agent и streaming size limit. До storage проверяются HTTP 200, MIME `application/pdf`, PDF
signature и checksum.

Manual endpoint принимает multipart только для существующего `(project_id, paper_id)` target в
`AWAITING_UPLOAD` и повторно проверяет `allow_manual_pdf_upload`. Успешный automatic или manual
write создаёт `PaperDocument`, связывает его с job и переводит job в `PARSING`; последующие parsing
шаги начинаются на этапе 9.

## State machine

Основной успешный путь:

```text
PENDING → DOWNLOADING → PARSING → CHUNKING → INDEXING → COMPLETED
```

Ветки отсутствующего автоматического PDF:

```text
PENDING/DOWNLOADING → AWAITING_UPLOAD
PENDING/DOWNLOADING → UNAVAILABLE
AWAITING_UPLOAD → PARSING
```

`404`, invalid MIME/signature и превышение size limit означают недоступный automatic source и
выбирают manual fallback policy. Исчерпанные timeout/transport/5xx retries дают `FAILED` только для
конкретной document job. ResearchJob к этому моменту уже завершён и не меняет результат.

Любое активное состояние может перейти в `FAILED`, если это явно разрешено domain state machine.
`COMPLETED`, `UNAVAILABLE` и `FAILED` terminal: неявный restart из них запрещён. Retry или новая
версия документа должны создаваться явной application operation, а не переписыванием истории.

## Version contracts

- `PaperDocument` имеет монотонную версию для пары `(paper, source)`. Одновременно активна только
  одна версия; одинаковый checksum переиспользует текущую версию.
- `ParsedDocument` уникален по `(document, parser_name, parser_version)` и хранит ссылку на
  оригинальный TEI, timestamps и ошибку.
- `DocumentElement` имеет уникальную позицию внутри parsed document. Типы: section, paragraph,
  table, figure caption, formula и bibliography.
- `CitationMarker` связывает элемент с соответствующим bibliography element. Удаление любого
  элемента каскадно удаляет связь.
- `PaperChunk` хранит canonical text, token offsets, element/section/page metadata, chunker и
  embedding versions. `stable_id` глобально уникален; одна позиция может иметь только одну active
  chunk version.

## Persistence order

```text
Paper
  ├─ DocumentProcessingJob (project target)
  └─ PaperDocument
       └─ ParsedDocument
            ├─ DocumentElement
            │    └─ CitationMarker
            └─ PaperChunk
```

`DocumentProcessingJob.document_id` остаётся `NULL` до появления PDF. Удаление конкретной версии
PDF устанавливает эту ссылку в `NULL`, но удаляет все parser-derived данные этой версии. Удаление
владельца `Paper` удаляет и сам target job, поэтому orphan records не остаются.
