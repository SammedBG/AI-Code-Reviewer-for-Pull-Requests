"""
Webhook Security Module

This module handles secure verification of GitHub webhook payloads.
It implements HMAC-SHA256 signature verification to ensure requests
are genuinely from GitHub.

Design Decisions:
- Use constant-time comparison to prevent timing attacks
- Verify signature before any payload processing
- Support both SHA-1 and SHA-256 signatures (SHA-256 preferred)
- Provide clear error messages for debugging
"""

import hashlib
import hmac
from typing import Optional

from fastapi import HTTPException, Request, status

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class WebhookSecurityError(Exception):
    """Custom exception for webhook security failures."""
    pass


async def verify_webhook_signature(
    request: Request,
    raw_body: bytes
) -> bool:
    """
    Verify the GitHub webhook signature.
    
    GitHub sends a signature in the X-Hub-Signature-256 header.
    We must verify this matches the HMAC-SHA256 of the request body
    using our webhook secret.
    
    Args:
        request: FastAPI request object
        raw_body: Raw request body bytes
        
    Returns:
        True if signature is valid
        
    Raises:
        HTTPException: If signature is missing or invalid
    """
    settings = get_settings()
    
    # Get the signature header
    # Prefer SHA-256, fall back to SHA-1
    signature_header = request.headers.get("X-Hub-Signature-256")
    algorithm = "sha256"
    
    if not signature_header:
        signature_header = request.headers.get("X-Hub-Signature")
        algorithm = "sha1"
    
    if not signature_header:
        logger.warning(
            "Missing webhook signature header",
            remote_addr=request.client.host if request.client else "unknown"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing webhook signature"
        )
    
    # Parse the signature
    try:
        prefix, signature = signature_header.split("=", 1)
        if prefix != algorithm:
            raise ValueError(f"Unexpected algorithm prefix: {prefix}")
    except ValueError as e:
        logger.warning(
            "Invalid signature format",
            signature_header=signature_header[:50],
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature format"
        )
    
    # Compute expected signature
    secret = settings.github_webhook_secret.encode()
    hash_func = hashlib.sha256 if algorithm == "sha256" else hashlib.sha1
    expected_signature = hmac.new(secret, raw_body, hash_func).hexdigest()
    
    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(signature, expected_signature):
        logger.warning(
            "Webhook signature mismatch",
            remote_addr=request.client.host if request.client else "unknown",
            algorithm=algorithm
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature"
        )
    
    logger.debug("Webhook signature verified successfully", algorithm=algorithm)
    return True


def validate_webhook_event(
    event_type: Optional[str],
    action: Optional[str]
) -> bool:
    """
    Validate that we should process this webhook event.
    
    We only process:
    - Event type: pull_request
    - Actions: opened, synchronize
    
    Args:
        event_type: GitHub event type from X-GitHub-Event header
        action: Action from payload
        
    Returns:
        True if we should process this event
        
    Raises:
        HTTPException: If event type is invalid
    """
    valid_event_types = {"pull_request"}
    valid_actions = {"opened", "synchronize"}
    
    if not event_type:
        logger.debug("Missing event type header")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-GitHub-Event header"
        )
    
    if event_type not in valid_event_types:
        logger.debug(
            "Ignoring non-PR event",
            event_type=event_type
        )
        return False
    
    if action and action not in valid_actions:
        logger.debug(
            "Ignoring PR action",
            action=action
        )
        return False
    
    return True


def extract_delivery_id(request: Request) -> Optional[str]:
    """
    Extract the webhook delivery ID from headers.
    
    This is useful for logging and idempotency checking.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Delivery ID or None
    """
    return request.headers.get("X-GitHub-Delivery")
