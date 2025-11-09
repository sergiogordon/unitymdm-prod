import pytest

from server.main import validate_single_command, build_batch_bloatware_disable_command, SessionLocal, BloatwarePackage


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


def test_build_batch_bloatware_disable_command_single_package():
    """Test batch command generation for a single package."""
    packages = ["com.example.app"]
    command = build_batch_bloatware_disable_command(packages)
    
    # Verify the command uses batch script approach
    assert "sh -c" in command
    assert "com.example.app" in command
    assert "while IFS= read -r pkg" in command
    assert "pm disable-user --user 0" in command
    assert "rm -f /data/local/tmp/bloat_list.txt" in command
    assert "2>/dev/null" in command  # Error suppression for graceful skipping


def test_build_batch_bloatware_disable_command_multiple_packages():
    """Test batch command generation for multiple packages."""
    packages = ["com.example.app.one", "com.example.app.two", "com.example.app.three"]
    command = build_batch_bloatware_disable_command(packages)
    
    # All packages should be included
    for pkg in packages:
        assert pkg in command
    
    # Verify batch structure
    assert "cat > /data/local/tmp/bloat_list.txt << 'EOF'" in command
    assert "EOF" in command
    assert "while IFS= read -r pkg" in command
    assert "done < /data/local/tmp/bloat_list.txt" in command


def test_build_batch_bloatware_disable_command_large_list():
    """Test that batch script handles large lists without command-line length issues."""
    # Create a list that would exceed command-line length if using && chaining
    packages = [f"com.package.app{i}" for i in range(200)]
    command = build_batch_bloatware_disable_command(packages)
    
    # Verify it uses temp file approach
    assert "/data/local/tmp/bloat_list.txt" in command
    assert "cat >" in command
    assert "while IFS= read -r pkg" in command
    # Verify no && chaining (which would be too long)
    assert command.count("&&") == 0


def test_build_batch_bloatware_disable_command_error_handling():
    """Test that the script includes error handling for missing packages."""
    packages = ["com.missing.app", "com.existing.app"]
    command = build_batch_bloatware_disable_command(packages)
    
    # Verify error suppression (2>/dev/null)
    assert "2>/dev/null" in command
    # Verify failure counter
    assert "failed=$((failed + 1))" in command
    # Verify success counter
    assert "count=$((count + 1))" in command
    # Verify summary output
    assert 'echo "Disabled $count packages ($failed skipped or failed)"' in command


def test_build_batch_bloatware_disable_command_empty_list():
    """Test batch command generation with empty list."""
    packages: list[str] = []
    command = build_batch_bloatware_disable_command(packages)
    
    # Should still generate a valid script, just with no packages
    assert "sh -c" in command
    assert "while IFS= read -r pkg" in command
    assert "rm -f /data/local/tmp/bloat_list.txt" in command

