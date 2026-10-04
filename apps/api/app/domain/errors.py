class DomainError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


class InvalidMedia(Exception):
    """A file cannot safely be processed. Retrying will not fix it."""
