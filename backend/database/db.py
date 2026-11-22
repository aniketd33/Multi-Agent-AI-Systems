"""
SQLite Database Module - Document Metadata Storage
Multi-Agent AI System for Finance and Business Insights
Developer: Aniket - Document Intelligence Agent Module

This module handles all database operations for storing and retrieving
document metadata using SQLite with async support.

FIXED: Threading issue resolved by using direct aiosqlite.connect()
"""

import aiosqlite
import os
from datetime import datetime
from typing import List, Dict, Optional
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# DATABASE CONFIGURATION
# ============================================

# Get project root directory (parent of backend)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

# Database file path (stored in project root)
DATABASE_PATH = os.environ.get(
    "DOCUMENTS_DATABASE_PATH",
    os.path.join(PROJECT_ROOT, "documents.db")
)

# ============================================
# DATABASE SCHEMA
# ============================================

# SQL schema for documents table
CREATE_DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    upload_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'uploaded',
    file_path TEXT NOT NULL,
    company_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


CREATE_RED_FLAG_TABLE = """
CREATE TABLE IF NOT EXISTS red_flag_analyses (
    document_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    findings_json TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    analyzed_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(document_id)
);
"""


# Create index for faster queries
CREATE_INDEX_STATUS = """
CREATE INDEX IF NOT EXISTS idx_status ON documents(status);
"""

CREATE_INDEX_UPLOAD_DATE = """
CREATE INDEX IF NOT EXISTS idx_upload_date ON documents(upload_date);
"""

# ============================================
# HELPER FUNCTIONS
# ============================================

def get_database_path() -> str:
    """
    Get the absolute path to the database file
    
    Returns:
        str: Absolute path to documents.db
    """
    return DATABASE_PATH

# ============================================
# DATABASE INITIALIZATION
# ============================================

async def initialize_database() -> bool:
    """
    Initialize the database and create tables if they don't exist
    
    This function:
    1. Creates the database file if it doesn't exist
    2. Creates the documents table with schema
    3. Creates indexes for performance
    
    Returns:
        bool: True if successful, False otherwise
        
    Example:
        success = await initialize_database()
    """
    try:
        logger.info(f"Initializing database at: {DATABASE_PATH}")
        
        # Create database connection - FIXED: Direct connection
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Create documents table
            await db.execute(CREATE_DOCUMENTS_TABLE)
            logger.info("✅ Documents table created/verified")
            
            # Create indexes
            await db.execute(CREATE_INDEX_STATUS)
            await db.execute(CREATE_INDEX_UPLOAD_DATE)
            logger.info("✅ Database indexes created/verified")
            await db.execute(CREATE_RED_FLAG_TABLE)
            logger.info("Red Flag analyses table created/verified")
            # Commit changes
            await db.commit()
            
        logger.info("✅ Database initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {str(e)}")
        return False

# ============================================
# CREATE OPERATIONS
# ============================================

async def insert_document(
    document_id: str,
    filename: str,
    file_type: str,
    file_size: int,
    file_path: str,
    status: str = "uploaded",
    company_name: Optional[str] = None
) -> bool:
    """
    Insert a new document record into the database
    
    Args:
        document_id: Unique UUID for the document
        filename: Original filename (e.g., "report.pdf")
        file_type: File extension (e.g., "PDF", "DOCX", "TXT")
        file_size: File size in bytes
        file_path: Absolute path where file is stored
        status: Document status (default: "uploaded")
        company_name: Optional company name for the document
        
    Returns:
        bool: True if successful, False otherwise
        
    Example:
        success = await insert_document(
            document_id="123e4567-e89b",
            filename="annual_report.pdf",
            file_type="PDF",
            file_size=1024000,
            file_path="/path/to/file.pdf"
        )
    """
    try:
        upload_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # FIXED: Direct connection without await in async with
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                """
                INSERT INTO documents (
                    document_id, filename, file_type, file_size,
                    upload_date, status, file_path, company_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    filename,
                    file_type,
                    file_size,
                    upload_date,
                    status,
                    file_path,
                    company_name
                )
            )
            await db.commit()
            
        logger.info(f"✅ Document inserted: {filename} (ID: {document_id})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to insert document: {str(e)}")
        return False

# ============================================
# READ OPERATIONS
# ============================================

async def get_all_documents() -> List[Dict]:
    """
    Retrieve all documents from the database
    
    Returns:
        List[Dict]: List of document records as dictionaries
        
    Example:
        documents = await get_all_documents()
        for doc in documents:
            print(doc['filename'], doc['status'])
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT 
                    document_id,
                    filename,
                    file_type,
                    file_size,
                    upload_date,
                    status,
                    file_path,
                    company_name
                FROM documents
                ORDER BY upload_date DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                
                # Convert Row objects to dictionaries
                documents = [dict(row) for row in rows]
                
        logger.info(f"✅ Retrieved {len(documents)} documents")
        return documents
        
    except Exception as e:
        logger.error(f"❌ Failed to retrieve documents: {str(e)}")
        return []


async def get_document_by_id(document_id: str) -> Optional[Dict]:
    """
    Retrieve a specific document by its ID
    
    Args:
        document_id: The unique document ID
        
    Returns:
        Optional[Dict]: Document record as dictionary, or None if not found
        
    Example:
        doc = await get_document_by_id("123e4567-e89b")
        if doc:
            print(f"Found: {doc['filename']}")
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT 
                    document_id,
                    filename,
                    file_type,
                    file_size,
                    upload_date,
                    status,
                    file_path,
                    company_name
                FROM documents
                WHERE document_id = ?
                """,
                (document_id,)
            ) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    document = dict(row)
                    logger.info(f"✅ Document found: {document['filename']}")
                    return document
                else:
                    logger.warning(f"⚠️  Document not found: {document_id}")
                    return None
                    
    except Exception as e:
        logger.error(f"❌ Failed to retrieve document: {str(e)}")
        return None


async def get_documents_by_status(status: str) -> List[Dict]:
    """
    Retrieve all documents with a specific status
    
    Args:
        status: Document status (e.g., "uploaded", "processing", "indexed")
        
    Returns:
        List[Dict]: List of matching documents
        
    Example:
        uploaded_docs = await get_documents_by_status("uploaded")
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT 
                    document_id,
                    filename,
                    file_type,
                    file_size,
                    upload_date,
                    status,
                    file_path,
                    company_name
                FROM documents
                WHERE status = ?
                ORDER BY upload_date DESC
                """,
                (status,)
            ) as cursor:
                rows = await cursor.fetchall()
                documents = [dict(row) for row in rows]
                
        logger.info(f"✅ Retrieved {len(documents)} documents with status: {status}")
        return documents
        
    except Exception as e:
        logger.error(f"❌ Failed to retrieve documents by status: {str(e)}")
        return []



async def get_documents_filtered(
    status: str = None,
    file_type: str = None,
    search: str = None
):
    """
    Retrieve documents with optional filters.

    All parameters are optional and combinable.

    Args:
        status:    Exact match on the status column  (e.g. "uploaded", "indexed")
        file_type: Exact match on the file_type column (e.g. "PDF", "TXT", "DOCX")
        search:    Case-insensitive substring match against the filename column

    Returns:
        List[Dict]: Matching document records, ordered by upload_date DESC.

    Note: Values are always passed as SQL parameters – never interpolated into
    the query string – so this function is safe against SQL injection.
    """
    try:
        conditions = []
        params = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status)

        if file_type is not None:
            conditions.append("file_type = ?")
            params.append(file_type)

        if search is not None:
            conditions.append("filename LIKE ?")
            params.append(f"%{search}%")

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""
            SELECT
                document_id, filename, file_type, file_size,
                upload_date, status, file_path, company_name
            FROM documents
            {where_clause}
            ORDER BY upload_date DESC
        """

        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                documents = [dict(row) for row in rows]

        logger.info(
            f"Filtered query returned {len(documents)} documents "
            f"(status={status!r}, file_type={file_type!r}, search={search!r})"
        )
        return documents

    except Exception as e:
        logger.error(f"Failed to retrieve filtered documents: {e}")
        return []
# ============================================
# UPDATE OPERATIONS
# ============================================

async def update_document_status(document_id: str, new_status: str) -> bool:
    """
    Update the status of a document
    
    Args:
        document_id: The unique document ID
        new_status: New status value (e.g., "processing", "indexed", "failed")
        
    Returns:
        bool: True if successful, False otherwise
        
    Example:
        success = await update_document_status("123e4567", "indexed")
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                """
                UPDATE documents
                SET status = ?
                WHERE document_id = ?
                """,
                (new_status, document_id)
            )
            await db.commit()
            
        logger.info(f"✅ Document status updated: {document_id} -> {new_status}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to update document status: {str(e)}")
        return False

# ============================================
# DELETE OPERATIONS
# ============================================

async def delete_document(document_id: str) -> bool:
    """
    Delete a document record from the database
    
    Note: This only deletes the database record, not the actual file.
    File deletion should be handled separately in the service layer.
    
    Args:
        document_id: The unique document ID
        
    Returns:
        bool: True if successful, False otherwise
        
    Example:
        success = await delete_document("123e4567-e89b")
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM documents WHERE document_id = ?",
                (document_id,)
            )
            await db.commit()
            
            # Check if any row was deleted
            if cursor.rowcount > 0:
                logger.info(f"✅ Document deleted: {document_id}")
                return True
            else:
                logger.warning(f"⚠️  Document not found: {document_id}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Failed to delete document: {str(e)}")
        return False

# ============================================
# UTILITY OPERATIONS
# ============================================

async def get_document_count() -> int:
    """
    Get the total number of documents in the database
    
    Returns:
        int: Total document count
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT COUNT(*) as count FROM documents") as cursor:
                row = await cursor.fetchone()
                count = row['count'] if row else 0
                
        logger.info(f"✅ Total documents: {count}")
        return count
        
    except Exception as e:
        logger.error(f"❌ Failed to get document count: {str(e)}")
        return 0


async def clear_all_documents() -> bool:
    """
    Delete all documents from the database
    
    WARNING: This is a destructive operation used mainly for testing.
    Use with caution!
    
    Returns:
        bool: True if successful
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("DELETE FROM documents")
            await db.commit()
            
        logger.info("✅ All documents cleared from database")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to clear documents: {str(e)}")
        return False

# ============================================
# DATABASE HEALTH CHECK
# ============================================

async def check_database_health() -> Dict:
    """
    Check database health and return statistics
    
    Returns:
        Dict: Database health information
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Get document count
            async with db.execute("SELECT COUNT(*) as count FROM documents") as cursor:
                row = await cursor.fetchone()
                total_docs = row['count'] if row else 0
            
            # Get status breakdown
            async with db.execute(
                """
                SELECT status, COUNT(*) as count 
                FROM documents 
                GROUP BY status
                """
            ) as cursor:
                status_rows = await cursor.fetchall()
                status_breakdown = {row['status']: row['count'] for row in status_rows}
        
        health_info = {
            "status": "healthy",
            "database_path": DATABASE_PATH,
            "database_exists": os.path.exists(DATABASE_PATH),
            "total_documents": total_docs,
            "status_breakdown": status_breakdown
        }
        
        logger.info("✅ Database health check completed")
        return health_info
        
    except Exception as e:
        logger.error(f"❌ Database health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

async def save_red_flag_analysis(
    document_id: str,
    status: str,
    findings: List[Dict],
    error: Optional[str] = None,
) -> bool:
    """Insert or update the Red Flag Agent result for a document."""
    try:
        analyzed_at = datetime.now().isoformat()
        findings_json = json.dumps(findings, ensure_ascii=False)

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                """
                INSERT INTO red_flag_analyses (
                    document_id, status, findings_json, error, analyzed_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    status = excluded.status,
                    findings_json = excluded.findings_json,
                    error = excluded.error,
                    analyzed_at = excluded.analyzed_at
                """,
                (document_id, status, findings_json, error, analyzed_at),
            )
            await db.commit()

        return True

    except Exception as exc:
        logger.exception("Failed to save Red Flag analysis: %s", exc)
        return False


async def get_red_flag_analysis(document_id: str) -> Optional[Dict]:
    """Retrieve the saved Red Flag Agent result."""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT document_id, status, findings_json, error, analyzed_at
                FROM red_flag_analyses
                WHERE document_id = ?
                """,
                (document_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        result = dict(row)
        result["findings"] = json.loads(result.pop("findings_json"))
        return result

    except Exception as exc:
        logger.exception("Failed to retrieve Red Flag analysis: %s", exc)
        return None
