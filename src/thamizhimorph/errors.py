"""Exceptions raised by ThamizhiMorph's application layer."""


class ThamizhiMorphError(Exception):
    """Base class for all package-specific errors."""


class ConfigurationError(ThamizhiMorphError):
    """Raised when model or runtime configuration is invalid."""


class BackendError(ThamizhiMorphError):
    """Raised when the finite-state backend cannot complete a lookup."""


class OptionalDependencyError(ThamizhiMorphError):
    """Raised when a requested optional integration is not installed."""


class DictionaryError(ThamizhiMorphError):
    """Raised when an external dictionary database is invalid or unavailable."""
