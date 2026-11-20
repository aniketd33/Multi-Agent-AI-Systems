"""
Database Package for Document Intelligence Agent
Handles SQLite database operations for document metadata storage
"""

from .db import (
    initialize_database,
    insert_document,
    get_all_documents,
    get_document_by_id,
    get_documents_by_status,
    get_documents_filtered,
    delete_document,
    update_document_status,
    get_document_count,
    clear_all_documents,
    check_database_health,
    get_database_path
)

__all__ = [
    "initialize_database",
    "insert_document",
    "get_all_documents",
    "get_document_by_id",
    "get_documents_by_status",
    "get_documents_filtered",
    "delete_document",
    "update_document_status",
    "get_document_count",
    "clear_all_documents",
    "check_database_health",
    "get_database_path"
]
