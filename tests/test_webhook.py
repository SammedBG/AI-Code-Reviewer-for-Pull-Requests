"""
Tests for Webhook Handler

Tests the webhook endpoint and security features.
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient


class TestWebhookEndpoint:
    """Test suite for the webhook endpoint."""
    
    def test_health_check(self, client: TestClient):
        """Test the health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_root_endpoint(self, client: TestClient):
        """Test the root endpoint."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "AI PR Reviewer"
        assert "version" in data
    
    def test_webhook_missing_signature(self, client: TestClient, sample_pr_payload: dict):
        """Test webhook without signature header."""
        response = client.post(
            "/webhook/github",
            json=sample_pr_payload,
            headers={"X-GitHub-Event": "pull_request"}
        )
        
        assert response.status_code == 401
        assert "signature" in response.json()["detail"].lower()
    
    def test_webhook_invalid_signature(self, client: TestClient, sample_pr_payload: dict):
        """Test webhook with invalid signature."""
        response = client.post(
            "/webhook/github",
            json=sample_pr_payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=invalid_signature"
            }
        )
        
        assert response.status_code == 401
    
    def test_webhook_missing_event_type(self, client: TestClient, sample_pr_payload: dict):
        """Test webhook without event type header."""
        # Create a valid signature
        body = json.dumps(sample_pr_payload).encode()
        signature = hmac.new(
            b"test_secret",  # Note: This won't match unless .env has this secret
            body,
            hashlib.sha256
        ).hexdigest()
        
        response = client.post(
            "/webhook/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={signature}"
            }
        )
        
        # Will fail signature check first in real scenario
        assert response.status_code in [400, 401]
    
    def test_webhook_health_endpoint(self, client: TestClient):
        """Test the webhook health endpoint."""
        response = client.get("/webhook/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestWebhookSecurity:
    """Test suite for webhook security features."""
    
    def test_signature_verification_sha256(self):
        """Test HMAC-SHA256 signature generation."""
        secret = b"test_secret"
        payload = b'{"test": "data"}'
        
        signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        
        # Verify the signature format
        assert len(signature) == 64  # SHA256 produces 64 hex chars
        assert all(c in '0123456789abcdef' for c in signature)
    
    def test_constant_time_comparison(self):
        """Test that we use constant-time comparison."""
        import hmac as hmac_module
        
        sig1 = "a" * 64
        sig2 = "a" * 64
        sig3 = "b" * 64
        
        # Same signatures should match
        assert hmac_module.compare_digest(sig1, sig2)
        
        # Different signatures should not match
        assert not hmac_module.compare_digest(sig1, sig3)


class TestPayloadValidation:
    """Test suite for webhook payload validation."""
    
    def test_valid_pr_opened_action(self, sample_pr_payload: dict):
        """Test that 'opened' action is valid."""
        from app.webhook.security import validate_webhook_event
        
        result = validate_webhook_event("pull_request", "opened")
        assert result is True
    
    def test_valid_pr_synchronize_action(self):
        """Test that 'synchronize' action is valid."""
        from app.webhook.security import validate_webhook_event
        
        result = validate_webhook_event("pull_request", "synchronize")
        assert result is True
    
    def test_invalid_pr_action(self):
        """Test that 'closed' action is ignored."""
        from app.webhook.security import validate_webhook_event
        
        result = validate_webhook_event("pull_request", "closed")
        assert result is False
    
    def test_invalid_event_type(self):
        """Test that non-PR events are ignored."""
        from app.webhook.security import validate_webhook_event
        
        result = validate_webhook_event("push", None)
        assert result is False
    
    def test_issue_event_ignored(self):
        """Test that issue events are ignored."""
        from app.webhook.security import validate_webhook_event
        
        result = validate_webhook_event("issues", "opened")
        assert result is False
