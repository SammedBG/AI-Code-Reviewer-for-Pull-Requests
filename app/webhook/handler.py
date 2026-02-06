"""
Webhook Handler Module

This module defines the FastAPI endpoints for handling GitHub webhooks.
It implements the webhook endpoint with proper security, validation,
and background task processing.

Design Decisions:
- Return 200 OK immediately after validation (GitHub timeout handling)
- Offload processing to background tasks
- Comprehensive logging for debugging
- Support for dry-run mode
"""

import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import ValidationError

from app.config import get_settings
from app.logging_config import get_logger
from app.models import PRContext, PullRequestWebhookPayload
from app.webhook.processor import process_pr_review
from app.webhook.security import (
    extract_delivery_id,
    validate_webhook_event,
    verify_webhook_signature,
)

logger = get_logger(__name__)

# Create router for webhook endpoints
router = APIRouter(prefix="/webhook", tags=["webhook"])

# Track active processing tasks for monitoring
_active_tasks: Dict[str, asyncio.Task] = {}


@router.post("/github", status_code=status.HTTP_200_OK)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    GitHub webhook endpoint.
    
    This endpoint receives webhook events from GitHub for pull requests.
    It validates the webhook signature, parses the payload, and queues
    the review for background processing.
    
    The endpoint returns immediately after validation to avoid
    GitHub's webhook timeout (10 seconds).
    
    Args:
        request: FastAPI request object
        background_tasks: FastAPI background tasks
        
    Returns:
        JSON response with status and delivery ID
        
    Raises:
        HTTPException: On validation or security failures
    """
    settings = get_settings()
    
    # Extract delivery ID for logging and tracking
    delivery_id = extract_delivery_id(request)
    
    logger.info(
        "Received GitHub webhook",
        delivery_id=delivery_id,
        remote_addr=request.client.host if request.client else "unknown"
    )
    
    # Read raw body for signature verification
    raw_body = await request.body()
    
    # Step 1: Verify webhook signature (security critical)
    await verify_webhook_signature(request, raw_body)
    
    # Step 2: Get event type from headers
    event_type = request.headers.get("X-GitHub-Event")
    
    # Step 3: Parse the payload
    try:
        payload_dict = await request.json() if raw_body else {}
    except Exception as e:
        logger.error("Failed to parse webhook payload", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    
    # Step 4: Validate event type and action
    action = payload_dict.get("action")
    if not validate_webhook_event(event_type, action):
        logger.debug(
            "Ignoring webhook event",
            event_type=event_type,
            action=action
        )
        return {
            "status": "ignored",
            "reason": f"Event type '{event_type}' with action '{action}' not processed",
            "delivery_id": delivery_id
        }
    
    # Step 5: Parse and validate the payload
    try:
        payload = PullRequestWebhookPayload(**payload_dict)
    except ValidationError as e:
        logger.error(
            "Invalid webhook payload",
            error=str(e),
            delivery_id=delivery_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payload: {e}"
        )
    
    # Step 6: Skip draft PRs
    if payload.pull_request.draft:
        logger.info(
            "Skipping draft PR",
            pr_number=payload.number,
            repo=payload.repository.full_name
        )
        return {
            "status": "ignored",
            "reason": "Draft PR",
            "delivery_id": delivery_id
        }
    
    # Step 7: Build PR context for processing
    pr_context = PRContext(
        owner=payload.repository.owner.login,
        repo=payload.repository.name,
        pr_number=payload.number,
        head_sha=payload.pull_request.head.sha,
        base_sha=payload.pull_request.base.sha,
        installation_id=payload.installation.id,
        title=payload.pull_request.title,
        body=payload.pull_request.body,
        author=payload.pull_request.user.login
    )
    
    logger.info(
        "Processing PR review",
        owner=pr_context.owner,
        repo=pr_context.repo,
        pr_number=pr_context.pr_number,
        action=action,
        author=pr_context.author,
        delivery_id=delivery_id
    )
    
    # Step 8: Queue background processing
    background_tasks.add_task(
        _process_review_with_error_handling,
        pr_context,
        delivery_id
    )
    
    # Return immediately - processing happens in background
    return {
        "status": "queued",
        "message": "PR review has been queued for processing",
        "delivery_id": delivery_id,
        "pr": {
            "owner": pr_context.owner,
            "repo": pr_context.repo,
            "number": pr_context.pr_number
        }
    }


async def _process_review_with_error_handling(
    pr_context: PRContext,
    delivery_id: Optional[str]
) -> None:
    """
    Process PR review with comprehensive error handling.
    
    This wrapper ensures that errors in background processing
    are properly logged and don't crash the server.
    
    Args:
        pr_context: Complete PR context
        delivery_id: Webhook delivery ID for tracking
    """
    task_id = f"{pr_context.full_repo_name}#{pr_context.pr_number}"
    
    logger.info(
        "Starting background review processing",
        task_id=task_id,
        delivery_id=delivery_id
    )
    
    try:
        result = await process_pr_review(pr_context)
        
        if result:
            logger.info(
                "Background review completed",
                task_id=task_id,
                delivery_id=delivery_id,
                num_issues=len(result.reviews)
            )
        else:
            logger.warning(
                "Background review returned no result",
                task_id=task_id,
                delivery_id=delivery_id
            )
            
    except Exception as e:
        logger.error(
            "Background review processing failed",
            task_id=task_id,
            delivery_id=delivery_id,
            error=str(e),
            error_type=type(e).__name__
        )
        # Don't re-raise - we don't want to crash background tasks


@router.get("/health")
async def webhook_health() -> Dict[str, str]:
    """
    Health check endpoint for the webhook service.
    
    Returns:
        Simple health status
    """
    return {"status": "healthy", "service": "webhook"}
