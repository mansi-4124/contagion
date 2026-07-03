class EdgarError(Exception):
    """Base exception for EDGAR client."""


class CompanyNotFoundError(EdgarError):
    """Raised when no matching company exists in EDGAR."""


class FilingNotFoundError(EdgarError):
    """Raised when the requested filing cannot be located."""