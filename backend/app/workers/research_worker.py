import asyncio
import json
import logging
import signal
from datetime import UTC, datetime
from uuid import UUID

from app.config import settings
from app.infrastructure.database import Database
from app.infrastructure.redis import RedisConnection
from app.providers.semantic_scholar import SemanticScholarProvider
from app.research.embeddings import EmbeddingService
from app.research.pipeline import ResearchPipeline


class ResearchWorker:
    """
    Минимальный Redis worker process для будущего ResearchPipeline.

    Attributes:
        redis (RedisConnection): Queue connection.
        queue_name (str): Redis list с research jobs.
        running (bool): Признак продолжения worker loop.

    Fallbacks:
        Invalid job записывается structured error и не останавливает worker.
    """

    def __init__(self) -> None:
        """
        Создаёт worker из environment settings.

        Returns:
            None: Метод инициализирует queue client.

        Fallbacks:
            Redis connection откладывается до первого BLPOP.
        """

        self.config = settings()
        self.database = Database(self.config)
        self.redis = RedisConnection(self.config)
        self.queue_name = self.config.worker_queue_name
        self.running = True

    async def process(self, project_id: UUID, job_id: UUID) -> None:
        """
        Выполняет один research pipeline job.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            job_id (UUID): Идентификатор persistent job.

        Returns:
            None: Pipeline сохраняет observable result в PostgreSQL.

        Fallbacks:
            Provider client закрывается даже при FAILED pipeline.
        """

        provider = SemanticScholarProvider(self.config)
        try:
            embedding_service = EmbeddingService(
                model_name=self.config.embedding_model_name,
                model_version=self.config.embedding_model_version,
                dimensions=self.config.embedding_dimensions,
                batch_size=self.config.embedding_batch_size,
            )
            pipeline = ResearchPipeline(
                self.database.session_factory,
                provider,
                embedding_service,
            )
            await pipeline.run(project_id, job_id)
        finally:
            await provider.close()

    def stop(self, signal_number: int, frame: object) -> None:
        """
        Запрашивает graceful остановку worker loop.

        Parameters:
            signal_number (int): Номер OS signal.
            frame (object): Текущий interpreter frame.

        Returns:
            None: Флаг running переключается в False.

        Fallbacks:
            Текущий blocking pop завершится не позднее чем через одну секунду.
        """

        self.running = False
        logging.info(
            json.dumps(
                {
                    "stage": "worker",
                    "status": "stopping",
                    "signal": signal_number,
                }
            )
        )

    def run(self) -> None:
        """
        Читает job envelopes из Redis queue.

        Returns:
            None: Цикл завершается после stop signal.

        Fallbacks:
            Invalid payload изолируется; Redis errors завершают process для container restart.
        """

        # Use a short blocking timeout to support graceful container shutdown.
        logging.info(json.dumps({"stage": "worker", "status": "started"}))
        try:
            while self.running:
                item = self.redis.client.blpop(self.queue_name, timeout=1)
                if item is None:
                    continue
                _, raw_payload = item
                started_at = datetime.now(UTC)
                try:
                    payload = json.loads(raw_payload)
                    project_id = UUID(payload["project_id"])
                    job_id = UUID(payload["job_id"])
                    asyncio.run(self.process(project_id, job_id))
                    logging.info(
                        json.dumps(
                            {
                                "project_id": str(project_id),
                                "job_id": str(job_id),
                                "stage": "worker_dispatch",
                                "duration": (datetime.now(UTC) - started_at).total_seconds(),
                                "status": "completed",
                            }
                        )
                    )
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                    logging.error(
                        json.dumps(
                            {
                                "stage": "worker_dispatch",
                                "duration": (datetime.now(UTC) - started_at).total_seconds(),
                                "status": "invalid_payload",
                                "error": str(error),
                            }
                        )
                    )
                except Exception as error:
                    logging.error(
                        json.dumps(
                            {
                                "project_id": payload.get("project_id"),
                                "job_id": payload.get("job_id"),
                                "stage": "worker_dispatch",
                                "duration": (datetime.now(UTC) - started_at).total_seconds(),
                                "status": "failed",
                                "error": str(error),
                            }
                        )
                    )
        finally:
            self.redis.close()
            self.database.dispose()


def main() -> None:
    """
    Настраивает logging, signals и запускает worker.

    Returns:
        None: Функция живёт до OS stop signal или Redis failure.

    Fallbacks:
        Unhandled infrastructure error завершает process с ненулевым exit code.
    """

    # Configure a stable timestamped stream for JSON structured messages.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    worker = ResearchWorker()
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    worker.run()


if __name__ == "__main__":
    main()
