"""
Custom domain exceptions.

WHY these live in core (not in api):
These describe *business-rule violations*, not HTTP errors.
The service/geo layers raise them; the API layer catches them and decides
which HTTP status code to return.  This keeps non-HTTP layers free of any
web-framework dependency — they stay testable as plain Python.
"""


class UnsupportedFileTypeError(Exception):
    """Raised when the uploaded file is not a .zip (Shapefile) or .kml."""

    def __init__(self, message: str = "File type is not supported") -> None:
        self.message = message
        super().__init__(self.message)


class FileTooLargeError(Exception):
    """Raised when the uploaded file exceeds MAX_UPLOAD_MB."""

    def __init__(self, message: str = "File exceeds size limit") -> None:
        self.message = message
        super().__init__(self.message)


class InvalidFileError(Exception):
    """Raised when the file is structurally broken (e.g. corrupt zip, missing .shp)."""

    def __init__(self, message: str = "File is invalid or unreadable") -> None:
        self.message = message
        super().__init__(self.message)


class NotFoundError(Exception):
    """Raised when a requested resource (e.g. file ID) does not exist."""

    def __init__(self, message: str = "Resource not found") -> None:
        self.message = message
        super().__init__(self.message)
