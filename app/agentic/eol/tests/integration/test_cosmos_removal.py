"""
Automated verification that all Cosmos DB references have been removed.
Created in Phase 11 to prevent Cosmos references from re-entering the codebase.
"""
import subprocess
import os
import pytest

EOL_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


class TestCosmosRemoval:
    """Verify complete Cosmos DB removal from the codebase."""

    def test_no_cosmos_imports_in_python(self):
        """No Python file under app/agentic/eol/ should import cosmos_cache or cve_cosmos_repository."""
        result = subprocess.run(
            ["grep", "-r", "--include=*.py", "-l",
             "from.*cosmos_cache import\\|import cosmos_cache\\|from.*cve_cosmos_repository import\\|import cve_cosmos_repository",
             EOL_ROOT],
            capture_output=True, text=True
        )
        matching_files = [f for f in result.stdout.strip().split("\n") if f and "__pycache__" not in f and "test_cosmos_removal" not in f]
        assert matching_files == [], f"Files still importing Cosmos modules: {matching_files}"

    def test_cosmos_cache_file_deleted(self):
        """cosmos_cache.py must not exist."""
        assert not os.path.exists(os.path.join(EOL_ROOT, "utils", "cosmos_cache.py")), \
            "utils/cosmos_cache.py still exists - should be deleted"

    def test_cve_cosmos_repository_file_deleted(self):
        """cve_cosmos_repository.py must not exist."""
        assert not os.path.exists(os.path.join(EOL_ROOT, "utils", "cve_cosmos_repository.py")), \
            "utils/cve_cosmos_repository.py still exists - should be deleted"

    def test_no_cosmos_test_files(self):
        """Cosmos-specific test files must not exist."""
        assert not os.path.exists(os.path.join(EOL_ROOT, "tests", "cache", "test_cosmos_cache.py")), \
            "tests/cache/test_cosmos_cache.py still exists"
        assert not os.path.exists(os.path.join(EOL_ROOT, "tests", "test_cve_cosmos_repository.py")), \
            "tests/test_cve_cosmos_repository.py still exists"

    def test_no_base_cosmos_usage_in_runtime(self):
        """No runtime Python file should reference base_cosmos (excluding tests and planning)."""
        result = subprocess.run(
            ["grep", "-r", "--include=*.py", "-l", "base_cosmos", EOL_ROOT],
            capture_output=True, text=True
        )
        matching_files = [f for f in result.stdout.strip().split("\n")
                         if f and "__pycache__" not in f and "/tests/" not in f and "test_cosmos_removal" not in f]
        assert matching_files == [], f"Runtime files still referencing base_cosmos: {matching_files}"

    def test_no_cosmos_in_requirements(self):
        """azure-cosmos should not be in requirements.txt."""
        req_path = os.path.join(EOL_ROOT, "requirements.txt")
        if os.path.exists(req_path):
            with open(req_path) as f:
                content = f.read()
            assert "azure-cosmos" not in content, "azure-cosmos still in requirements.txt"

    def test_no_cosmos_config_fields(self):
        """config.py should not contain Cosmos config fields."""
        config_path = os.path.join(EOL_ROOT, "utils", "config.py")
        with open(config_path) as f:
            content = f.read()
        cosmos_lines = [line.strip() for line in content.split("\n")
                       if "cosmos" in line.lower() and not line.strip().startswith("#")]
        assert cosmos_lines == [], f"config.py still has Cosmos config: {cosmos_lines}"

    def test_no_cosmos_endpoints_in_main(self):
        """main.py should not have /api/cache/cosmos/ endpoints."""
        main_path = os.path.join(EOL_ROOT, "main.py")
        with open(main_path) as f:
            content = f.read()
        assert "/api/cache/cosmos/" not in content, "main.py still has Cosmos API endpoints"

    def test_no_cosmos_settings_in_deploy_config(self):
        """Deployment config should not define Cosmos settings."""
        targets = [
            os.path.join(EOL_ROOT, "deploy", "appsettings.json.example"),
            os.path.join(EOL_ROOT, "deploy", "generate-appsettings.sh"),
            os.path.join(EOL_ROOT, "deploy", "deploy-container.sh"),
        ]
        for target in targets:
            with open(target) as f:
                content = f.read()
            assert "CosmosDB" not in content, f"{target} still defines CosmosDB settings"
            assert "AZURE_COSMOS_DB_" not in content, f"{target} still injects Cosmos env vars"
