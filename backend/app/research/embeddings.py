from app.domain.embedding import (
    EmbeddedPaper,
    EmbeddedQuestion,
    EmbeddingFailure,
    PaperEmbeddingBatch,
    QuestionEmbeddingBatch,
)
from app.domain.paper import Paper
from app.domain.project import ResearchQuestion


class EmbeddingService:
    """
    Создаёт normalized scientific embeddings одним SentenceTransformer model.

    Attributes:
        model_name (str): Hugging Face или local model identifier.
        model_version (str): Версия persistence contract.
        dimensions (int): Ожидаемая размерность vectors.

    Fallbacks:
        Failed batch повторяется по одной entity для failure isolation.
    """

    def __init__(
        self,
        model_name: str,
        model_version: str,
        dimensions: int,
        batch_size: int,
        encoder: object | None = None,
    ) -> None:
        """
        Настраивает lazy SentenceTransformer backend.

        Parameters:
            model_name (str): Model identifier.
            model_version (str): Версия model/pooling configuration.
            dimensions (int): Ожидаемая размерность embedding.
            batch_size (int): Inference batch size.
            encoder (object | None): Injected fixture encoder. По умолчанию: None.

        Returns:
            None: Метод инициализирует service.

        Fallbacks:
            Model загружается только при первом реальном embed request.
        """

        if dimensions < 1 or batch_size < 1:
            raise ValueError("Embedding dimensions and batch_size must be positive")
        self.model_name = model_name
        self.model_version = model_version
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.encoder = encoder

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Кодирует text batch в normalized vectors.

        Parameters:
            texts (list[str]): Тексты из одного embedding space.

        Returns:
            list[list[float]]: Vectors в исходном порядке.

        Fallbacks:
            Empty input не загружает model и возвращает пустой список.
        """

        if not texts:
            return []
        if self.encoder is None:
            from sentence_transformers import SentenceTransformer

            self.encoder = SentenceTransformer(self.model_name, trust_remote_code=False)
        model_dimensions = self.encoder.get_sentence_embedding_dimension()
        if model_dimensions != self.dimensions:
            raise ValueError(
                f"Embedding model returns {model_dimensions} dimensions; "
                f"configured {self.dimensions}"
            )
        encoded = self.encoder.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        raw_vectors = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        vectors = [[float(value) for value in vector] for vector in raw_vectors]
        if len(vectors) != len(texts) or any(len(vector) != self.dimensions for vector in vectors):
            raise ValueError("Embedding backend returned an invalid batch shape")
        return vectors

    def embed_papers(self, papers: list[Paper]) -> PaperEmbeddingBatch:
        """
        Кодирует title + abstract papers с batching и failure isolation.

        Parameters:
            papers (list[Paper]): Глобальные papers.

        Returns:
            PaperEmbeddingBatch: Успешные vectors и per-paper failures.

        Fallbacks:
            Missing abstract оставляет title-only text, а не zero vector.
        """

        result = PaperEmbeddingBatch()
        for offset in range(0, len(papers), self.batch_size):
            batch = papers[offset : offset + self.batch_size]
            texts = [f"{paper.title} [SEP] {paper.abstract or ''}" for paper in batch]
            try:
                vectors = self.embed_texts(texts)
                result.embeddings.extend(
                    EmbeddedPaper(paper_id=paper.id, vector=vector)
                    for paper, vector in zip(batch, vectors, strict=True)
                )
            except Exception:
                # Retry individually to isolate one malformed or oversized paper.
                for paper, text in zip(batch, texts, strict=True):
                    try:
                        vector = self.embed_texts([text])[0]
                        result.embeddings.append(EmbeddedPaper(paper.id, vector))
                    except Exception as error:
                        result.failures.append(EmbeddingFailure(paper.id, str(error)))
        return result

    def embed_questions(self, questions: list[ResearchQuestion]) -> QuestionEmbeddingBatch:
        """
        Кодирует research questions тем же model space.

        Parameters:
            questions (list[ResearchQuestion]): Вопросы текущего проекта.

        Returns:
            QuestionEmbeddingBatch: Успешные vectors и per-question failures.

        Fallbacks:
            Failed batch повторяется по одному вопросу.
        """

        result = QuestionEmbeddingBatch()
        for offset in range(0, len(questions), self.batch_size):
            batch = questions[offset : offset + self.batch_size]
            texts = [question.text for question in batch]
            try:
                vectors = self.embed_texts(texts)
                result.embeddings.extend(
                    EmbeddedQuestion(question_id=question.id, vector=vector)
                    for question, vector in zip(batch, vectors, strict=True)
                )
            except Exception:
                # Retry individually so one invalid question does not break the project.
                for question in batch:
                    try:
                        vector = self.embed_texts([question.text])[0]
                        result.embeddings.append(EmbeddedQuestion(question.id, vector))
                    except Exception as error:
                        result.failures.append(EmbeddingFailure(question.id, str(error)))
        return result
