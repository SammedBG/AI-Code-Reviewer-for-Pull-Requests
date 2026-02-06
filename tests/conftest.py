"""
Test Configuration

Pytest configuration and fixtures for the test suite.
"""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create a test client for synchronous tests."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_pr_payload() -> dict:
    """Sample pull request webhook payload."""
    return {
        "action": "opened",
        "number": 42,
        "pull_request": {
            "id": 123456789,
            "number": 42,
            "state": "open",
            "title": "Add new feature",
            "body": "This PR adds a new feature to the application.",
            "user": {
                "login": "testuser",
                "id": 12345,
                "type": "User"
            },
            "html_url": "https://github.com/owner/repo/pull/42",
            "diff_url": "https://github.com/owner/repo/pull/42.diff",
            "patch_url": "https://github.com/owner/repo/pull/42.patch",
            "head": {
                "ref": "feature-branch",
                "sha": "abc123def456",
                "repo": {
                    "id": 111,
                    "name": "repo",
                    "full_name": "owner/repo",
                    "private": False,
                    "owner": {
                        "login": "owner",
                        "id": 1,
                        "type": "User"
                    },
                    "html_url": "https://github.com/owner/repo",
                    "default_branch": "main"
                }
            },
            "base": {
                "ref": "main",
                "sha": "xyz789abc012",
                "repo": None
            },
            "merged": False,
            "draft": False,
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z"
        },
        "repository": {
            "id": 111,
            "name": "repo",
            "full_name": "owner/repo",
            "private": False,
            "owner": {
                "login": "owner",
                "id": 1,
                "type": "User"
            },
            "html_url": "https://github.com/owner/repo",
            "default_branch": "main"
        },
        "sender": {
            "login": "testuser",
            "id": 12345,
            "type": "User"
        },
        "installation": {
            "id": 987654
        }
    }


@pytest.fixture
def sample_diff_patch() -> str:
    """Sample unified diff patch."""
    return '''@@ -1,5 +1,7 @@
 import os
+import sys
 
 def main():
-    print("Hello")
+    name = input("Enter name: ")
+    print(f"Hello, {name}!")
     return 0
'''
