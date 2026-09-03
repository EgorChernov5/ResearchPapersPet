from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import Settings


class Base(DeclarativeBase):
    """
    Базовый класс SQLAlchemy-моделей.

    Fallbacks:
        Не содержит бизнес-логики и используется только инфраструктурным слоем.
    """


class Database:
    """
    Управляет SQLAlchemy engine и фабрикой сессий.

    Attributes:
        engine (Engine): Пул подключений к PostgreSQL.
        session_factory (sessionmaker): Фабрика транзакционных сессий.

    Fallbacks:
        Ошибка подключения передаётся вызывающему коду для health-check или job failure.
    """

    def __init__(self, config: Settings) -> None:
        """
        Создаёт инфраструктуру доступа к базе данных.

        Parameters:
            config (Settings): Конфигурация приложения.

        Returns:
            None: Метод инициализирует объект.

        Fallbacks:
            Фактическое соединение откладывается до первого запроса.
        """

        self.engine = create_engine(config.database_url, pool_pre_ping=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def dispose(self) -> None:
        """
        Закрывает пул подключений.

        Returns:
            None: Ресурсы engine освобождаются.

        Fallbacks:
            Повторный вызов безопасно обрабатывается SQLAlchemy.
        """

        self.engine.dispose()
