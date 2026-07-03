from __future__ import annotations

from app.config.settings import settings
from app.config.logging import get_logger


class EdgarClient:
    """
    Lightweight asynchronous client for interacting with the SEC EDGAR APIs.

    This class will gradually be expanded throughout D2-01 following
    the TDD cycle.
    """

    BASE_URL = "https://www.sec.gov"

    def __init__(self) -> None:
        self.settings = settings
        self.logger = get_logger(__name__)