"""Custom exception types for swoop."""


class SwoopError(Exception):
    """Base exception for all swoop errors."""


class SwoopHTTPError(SwoopError):
    """Raised when Google Flights returns a non-200 HTTP response.

    Attributes:
        status_code: The HTTP status code returned.
    """

    def __init__(self, status_code: int, message: str | None = None):
        self.status_code = status_code
        if message is None:
            message = f"Google Flights returned HTTP {status_code}"
        super().__init__(message)


class SwoopRateLimitError(SwoopHTTPError):
    """Raised when Google Flights returns HTTP 429 (Too Many Requests)."""

    def __init__(self) -> None:
        super().__init__(
            429,
            "Google Flights rate limit hit (HTTP 429). "
            "Wait a few minutes before retrying.",
        )


class SwoopParseError(SwoopError):
    """Raised when the response from Google Flights cannot be parsed."""
