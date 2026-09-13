"""Domain-specific exceptions."""


class DomainValidationError(ValueError):
    """Raised when canonical domain data violates an invariant."""
