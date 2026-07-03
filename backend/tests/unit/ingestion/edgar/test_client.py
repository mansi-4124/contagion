import pytest

from app.ingestion.edgar import EdgarClient


def test_client_can_be_created():
    """
    Smallest possible test.

    If this fails,
    imports or constructor are broken.
    """

    client = EdgarClient()

    assert client is not None