"""
FastAPI Application Entry Point

This module creates and configures the FastAPI application.
It sets up all routes, middleware, and exception handlers.

Design Decisions:
- Use lifespan events for startup/shutdown
- Add CORS middleware for flexibility
- Include comprehensive error handling
- Expose health check endpoints
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.logging_config import get_logger, setup_logging
from app.webhook import router as webhook_router

# Initialize logging first
setup_logging()

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    
    Handles startup and shutdown events for the application.
    """
    # Startup
    logger.info(
        "Starting AI PR Reviewer",
        host=get_settings().host,
        port=get_settings().port
    )
    
    # Validate configuration on startup
    try:
        settings = get_settings()
        # Test that we can load the private key
        settings.get_private_key()
        logger.info("Configuration validated successfully")
    except Exception as e:
        logger.error(
            "Configuration validation failed",
            error=str(e)
        )
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down AI PR Reviewer")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application instance
    """
    settings = get_settings()
    
    app = FastAPI(
        title="AI PR Reviewer",
        description="AI-powered GitHub Pull Request code reviewer",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Register routes
    app.include_router(webhook_router)
    
    # Add global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request,
        exc: Exception
    ) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            error_type=type(exc).__name__
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "type": type(exc).__name__
            }
        )
    
    # Add root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with basic info."""
        return {
            "name": "AI PR Reviewer",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs"
        }
    
    # Add health check endpoint
    @app.get("/health")
    async def health_check():
        """
        Health check endpoint.
        
        Returns basic health status for load balancers and monitors.
        """
        return {
            "status": "healthy",
            "service": "ai-pr-reviewer",
            "version": "1.0.0"
        }
    
    # Add readiness check endpoint
    @app.get("/ready")
    async def readiness_check():
        """
        Readiness check endpoint.
        
        Verifies that the application is ready to handle requests.
        """
        try:
            # Verify configuration is valid
            settings = get_settings()
            settings.get_private_key()
            
            return {
                "status": "ready",
                "service": "ai-pr-reviewer"
            }
        except Exception as e:
            logger.error("Readiness check failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Not ready: {e}"
            )
    
    return app


# Create the application instance
app = create_app()
