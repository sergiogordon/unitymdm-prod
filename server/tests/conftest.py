"""
Pytest configuration and shared fixtures for acceptance tests.
"""
import pytest
import os
import sys
from typing import Generator, Dict
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Base, get_db, User, Device
from main import app
from auth import hash_password, hash_token, generate_device_token, compute_token_id


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    """
    Create a clean test database for each test.
    Uses in-memory SQLite for fast test execution.
    """
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
    
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    Base.metadata.create_all(bind=engine)
    
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db: Session) -> TestClient:
    """
    Create a test client with dependency overrides.
    """
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    client = TestClient(app)
    yield client
    
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def admin_user(test_db: Session) -> User:
    """
    Create an admin user for testing.
    """
    user = User(
        username="test_admin",
        email="admin@test.com",
        password_hash=hash_password("admin123")
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture(scope="function")
def admin_auth(client: TestClient, admin_user: User) -> Dict[str, str]:
    """
    Return admin authentication headers.
    """
    response = client.post("/api/auth/login", json={
        "username": "test_admin",
        "password": "admin123"
    })
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def admin_key() -> Dict[str, str]:
    """
    Return admin key headers.
    """
    admin_key = os.getenv("ADMIN_KEY", "admin")
    return {"X-Admin": admin_key}


@pytest.fixture(scope="function")
def test_device(test_db: Session) -> tuple[Device, str]:
    """
    Create a test device and return it with its bearer token.
    Returns: (device, raw_token)
    """
    raw_token = generate_device_token()
    token_hash = hash_token(raw_token)
    token_id = compute_token_id(raw_token)
    
    device = Device(
        id=f"test_device_001",
        alias="Test Device 001",
        token_hash=token_hash,
        token_id=token_id,
        app_version="1.0.0"
    )
    test_db.add(device)
    test_db.commit()
    test_db.refresh(device)
    
    return (device, raw_token)


@pytest.fixture(scope="function")
def device_auth(test_device: tuple[Device, str]) -> Dict[str, str]:
    """
    Return device authentication headers.
    """
    _, raw_token = test_device
    return {"Authorization": f"Bearer {raw_token}"}


@pytest.fixture(scope="function")
def capture_logs(monkeypatch):
    """
    Capture structured logs emitted during tests.
    """
    logs = []
    
    from observability import StructuredLogger
    
    original_log_event = StructuredLogger.log_event
    
    def capture_log_event(self, event: str, level: str = "INFO", **fields):
        logs.append({
            "event": event,
            "level": level,
            **fields
        })
        original_log_event(self, event, level, **fields)
    
    monkeypatch.setattr(StructuredLogger, "log_event", capture_log_event)
    
    return logs


@pytest.fixture(scope="function")
def capture_metrics(monkeypatch):
    """
    Capture metrics emitted during tests.
    """
    metrics_data = {
        "counters": [],
        "histograms": []
    }
    
    from observability import MetricsCollector
    
    original_inc_counter = MetricsCollector.inc_counter
    original_observe_histogram = MetricsCollector.observe_histogram
    
    def capture_counter(self, metric_name: str, labels=None, value: int = 1):
        metrics_data["counters"].append({
            "name": metric_name,
            "labels": labels or {},
            "value": value
        })
        original_inc_counter(self, metric_name, labels, value)
    
    def capture_histogram(self, metric_name: str, value: float, labels=None):
        metrics_data["histograms"].append({
            "name": metric_name,
            "value": value,
            "labels": labels or {}
        })
        original_observe_histogram(self, metric_name, value, labels)
    
    monkeypatch.setattr(MetricsCollector, "inc_counter", capture_counter)
    monkeypatch.setattr(MetricsCollector, "observe_histogram", capture_histogram)
    
    return metrics_data
