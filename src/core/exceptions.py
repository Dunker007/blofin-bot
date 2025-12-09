"""Custom exceptions for Blofin Bot."""


class BlofinBotError(Exception):
    """Base exception for all bot errors."""
    pass


class APIError(BlofinBotError):
    """Blofin API related errors."""
    
    def __init__(self, message: str, code: str = None, response: dict = None):
        super().__init__(message)
        self.code = code
        self.response = response or {}
    
    def __str__(self):
        if self.code:
            return f"[{self.code}] {super().__str__()}"
        return super().__str__()


class ConfigError(BlofinBotError):
    """Configuration related errors."""
    pass


class AuthenticationError(APIError):
    """Authentication/signature errors."""
    pass


class RateLimitError(APIError):
    """Rate limit exceeded."""
    pass


class InsufficientFundsError(APIError):
    """Not enough margin/balance."""
    pass


class PositionError(BlofinBotError):
    """Position-related errors."""
    pass


class OrderError(BlofinBotError):
    """Order placement/cancellation errors."""
    pass
