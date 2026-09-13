"""Errors raised by the provider-independent arbitrage mathematics core."""


class ArbitrageMathError(ValueError):
    """Base error for invalid mathematical inputs or incompatible canonical books."""


class IncompleteMarketError(ArbitrageMathError):
    """Raised when a candidate book does not contain exactly the expected outcomes."""


class StakeConstraintError(ArbitrageMathError):
    """Raised when stake constraints or rounding policy are internally invalid."""
