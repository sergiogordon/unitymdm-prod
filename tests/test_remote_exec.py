import pytest

from server.main import validate_single_command, SessionLocal, BloatwarePackage


@pytest.fixture(autouse=True)
def setup_bloatware_table(monkeypatch):
    """
    Ensure the bloatware table contains a known package for validation tests.
    """
    db = SessionLocal()
    try:
        # Remove existing entries to ensure deterministic outcome
        db.query(BloatwarePackage).delete()
        db.add(BloatwarePackage(package_name="com.example.goodapp", enabled=True))
        db.commit()
    finally:
        db.close()


def test_validate_single_command_allows_known_bloatware(monkeypatch):
    is_valid, error = validate_single_command("pm disable-user --user 0 com.example.goodapp")
    assert is_valid, f"Expected command to be valid, but failed with: {error}"


def test_validate_single_command_rejects_unknown_bloatware(monkeypatch):
    is_valid, error = validate_single_command("pm disable-user --user 0 com.example.unknown")
    assert not is_valid
    assert "not in the enabled bloatware list" in error

