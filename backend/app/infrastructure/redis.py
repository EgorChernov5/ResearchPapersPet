from redis import Redis

from app.config import Settings


class RedisConnection:
    """
    Управляет синхронным подключением к Redis.

    Attributes:
        client (Redis): Клиент очереди и health-check.

    Fallbacks:
        Сетевые ошибки передаются вызывающему коду.
    """

    def __init__(self, config: Settings) -> None:
        """
        Создаёт Redis-клиент без немедленного подключения.

        Parameters:
            config (Settings): Конфигурация приложения.

        Returns:
            None: Метод инициализирует объект.

        Fallbacks:
            Соединение устанавливается при первой команде.
        """

        self.client = Redis.from_url(config.redis_url, decode_responses=True)

    def close(self) -> None:
        """
        Закрывает пул Redis-соединений.

        Returns:
            None: Ресурсы клиента освобождаются.

        Fallbacks:
            Повторное закрытие допускается Redis-клиентом.
        """

        self.client.close()
