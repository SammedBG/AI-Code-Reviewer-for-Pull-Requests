"""
Application Runner

This script is the entry point for running the application.
Use: python run.py
"""

import sys
from pathlib import Path

# Add project root to Python path to enable 'app' module imports
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

import uvicorn

from app.config import get_settings


def main():
    """Run the application with uvicorn."""
    settings = get_settings()
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,  # Disable for production
        log_level=settings.log_level.lower(),
        access_log=settings.log_requests
    )


if __name__ == "__main__":
    main()
