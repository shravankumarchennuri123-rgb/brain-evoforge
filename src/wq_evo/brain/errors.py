from __future__ import annotations

class BrainError(Exception):
    """Base class for typed BRAIN integration failures."""

class RetryableBrainError(BrainError):
    pass

class RateLimitError(RetryableBrainError):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after

class PermissionErrorBrain(BrainError):
    pass

class PersonaRequiredError(BrainError):
    pass

class BudgetUnknownError(BrainError):
    pass

class BudgetExhaustedError(BrainError):
    pass

class SchemaDriftError(BrainError):
    pass

class TerminalSubmitError(BrainError):
    pass
