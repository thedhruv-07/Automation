import mongomock
import pytest


@pytest.fixture
def mongo_db():
    return mongomock.MongoClient()["cert_dashboard_test"]
