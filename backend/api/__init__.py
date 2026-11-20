"""
API Package
REST API endpoints for document operations
"""

from .documents import router as documents_router

__all__ = ["documents_router"]
