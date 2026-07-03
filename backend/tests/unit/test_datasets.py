import uuid
from app.cognee.datasets import namespace_for
from app.config.settings import settings


def test_namespace_for_matches_expected_format():
    test_id = uuid.uuid4()
    result = namespace_for(test_id)
    assert result == f"company_{test_id}_v{settings.cognee.default_schema_version}"


def test_namespace_for_default_schema_version_is_1():
    test_id = uuid.uuid4()
    result = namespace_for(test_id)
    assert result.endswith("_v1")


def test_namespace_for_is_deterministic():
    test_id = uuid.uuid4()
    assert namespace_for(test_id) == namespace_for(test_id)


def test_namespace_for_differs_across_ids():
    assert namespace_for(uuid.uuid4()) != namespace_for(uuid.uuid4())