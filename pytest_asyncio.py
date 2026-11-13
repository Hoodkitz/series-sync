"""Minimal stub for pytest_asyncio used in the test-runner environment where the package
may be unavailable. This stub maps pytest_asyncio.fixture to pytest.fixture so async tests
that run synchronously via event loop helpers can still be discovered.

NOTE: This is a test-time stub only and should NOT be used in production. Prefer installing
pytest-asyncio in the environment where the test suite runs.
"""
import pytest

# Provide decorator used in tests: @pytest_asyncio.fixture
fixture = pytest.fixture

# Expose a plugin marker so tests that check pytest_plugins find it.
pytest_plugins = ()
