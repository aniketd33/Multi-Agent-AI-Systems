"""
Documents API Endpoints
Handles document upload, listing, retrieval, and deletion
Multi-Agent AI System for Finance and Business Insights
Developer: Aniket - Document Intelligence Agent Module
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, status
from fastapi.responses import JSONResponse
from typing import List, Optional
import logging
from pathlib import Path

# Import our services and database
from backend.services.upload import process_upload, delete_file
from backend.database import (
    insert_document,
    get_all_documents,
    get_documents_filtered,
    get_document_by_id,
    delete_document as db_delete_document
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create API router
router = APIRouter(prefix="/api/documents", tags=["documents"])

# ============================================
# UPLOAD ENDPOINT
# ============================================

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...)
):
    """
    Upload a document (PDF, DOCX, or TXT)
    
    This endpoint:
    1. Receives the uploaded file
    2. Validates file type and size
    3. Saves file to disk
    4. Stores metadata in database
    5. Returns document information
    
    Args:
        file: Uploaded file (multipart/form-data)
        
    Returns:
        JSON response with document details
        
    Raises:
        HTTPException: If validation fails or upload error occurs
        
    Example Success Response:
        {
            "status": "success",
            "message": "Document uploaded successfully",
            "document": {
                "document_id": "123e4567-e89b-12d3-a456-426614174000",
                "filename": "report.pdf",
                "file_type": "PDF",
                "file_size": 1024000,
                "upload_date": "2024-01-15 10:30:00",
                "status": "uploaded"
            }
        }
        
    Example Error Response:
        {
            "status": "error",
            "message": "File too large (25.5 MB). Maximum allowed: 20 MB"
        }
    """
    
    try:
        logger.info(f"📤 Upload request received: {file.filename}")
        
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        logger.info(f"File size: {file_size} bytes ({file_size / 1024:.2f} KB)")
        
        # Process upload (validation + storage)
        result = await process_upload(
            file_content=file_content,
            filename=file.filename,
            file_size=file_size
        )
        
        # Check if upload processing failed
        if not result.get("success"):
            error_message = result.get("error", "Upload processing failed")
            logger.error(f"❌ Upload failed: {error_message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
        
        # Extract upload result
        document_id = result["document_id"]
        filename = result["filename"]
        file_type = result["file_type"]
        file_size = result["file_size"]
        file_path = result["file_path"]
        upload_date = result["upload_date"]
        
        # Store metadata in database
        logger.info(f"💾 Storing metadata in database...")
        db_success = await insert_document(
            document_id=document_id,
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            file_path=file_path,
            status="uploaded"
        )
        
        # If database insertion fails, delete the uploaded file
        if not db_success:
            logger.error("❌ Database insertion failed, cleaning up file...")
            delete_file(Path(file_path))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store document metadata. File removed."
            )
        
        # Success response
        response_data = {
            "status": "success",
            "message": "Document uploaded successfully",
            "document": {
                "document_id": document_id,
                "filename": filename,
                "file_type": file_type,
                "file_size": file_size,
                "upload_date": upload_date,
                "status": "uploaded"
            }
        }
        
        logger.info(f"✅ Upload complete: {filename} (ID: {document_id})")
        
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response_data
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
        
    except Exception as e:
        logger.error(f"❌ Unexpected error during upload: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


# ============================================
# LIST DOCUMENTS ENDPOINT (Placeholder for Stage 5)
# ============================================

@router.get("/")
async def list_documents(
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by document status (e.g. uploaded, processing, indexed, failed)"
    ),
    file_type: Optional[str] = Query(
        default=None,
        description="Filter by file type (PDF, DOCX, TXT)"
    ),
    search: Optional[str] = Query(
        default=None,
        description="Case-insensitive substring search on filename"
    ),
):
    """
    List documents with optional filters.

    Query parameters (all optional, combinable):
      - status    : exact match on document status
      - file_type : exact match on file type
      - search    : substring match on filename

    Returns all documents when no filters are supplied.
    """
    try:
        any_filter = status_filter is not None or file_type is not None or search is not None
        if any_filter:
            logger.info(
                f"Fetching documents (status={status_filter!r}, "
                f"file_type={file_type!r}, search={search!r})"
            )
            documents = await get_documents_filtered(
                status=status_filter,
                file_type=file_type,
                search=search,
            )
        else:
            logger.info("Fetching all documents (no filters)")
            documents = await get_all_documents()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "count": len(documents),
                "documents": documents,
            }
        )

    except Exception as e:
        logger.error(f"Failed to fetch documents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch documents: {e}"
        )

# ============================================
# GET DOCUMENT BY ID ENDPOINT (Placeholder for Stage 5)
# ============================================

@router.get("/{document_id}")
async def get_document(document_id: str):
    """
    Get details of a specific document
    
    Args:
        document_id: Unique document ID
        
    Returns:
        JSON response with document details
        
    Note: Full implementation in Stage 5
    """
    try:
        logger.info(f"🔍 Fetching document: {document_id}")
        document = await get_document_by_id(document_id)
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {document_id}"
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "document": document
            }
        )
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch document: {str(e)}"
        )


# ============================================
# DELETE DOCUMENT ENDPOINT (Placeholder for Stage 5)
# ============================================

@router.delete("/{document_id}")
async def delete_document_endpoint(document_id: str):
    """
    Delete a document
    
    Args:
        document_id: Unique document ID
        
    Returns:
        JSON response confirming deletion
        
    Note: Full implementation in Stage 5
    """
    try:
        logger.info(f"🗑️  Deleting document: {document_id}")
        
        # Get document info first
        document = await get_document_by_id(document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {document_id}"
            )
        
        # Delete from database
        db_success = await db_delete_document(document_id)
        if not db_success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete document from database"
            )
        
        # Delete physical file
        file_path = Path(document['file_path'])
        if file_path.exists():
            delete_file(file_path)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "message": f"Document deleted: {document['filename']}"
            }
        )
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"❌ Failed to delete document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )
