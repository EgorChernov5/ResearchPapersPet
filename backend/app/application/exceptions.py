class ResourceNotFoundError(ValueError):
    """
    Обозначает отсутствие запрошенной application entity.

    Fallbacks:
        API layer преобразует исключение в HTTP 404.
    """
