"""
Documents API Endpoints
Handles document upload, listing, retrieval, and deletion
Multi-Agent AI System for Finance and Business Insights
Developer: Aniket - Document Intelligence Agent Module
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse

# Import our services and database
from backend.services.upload import process_upload, delete_file
from backend.database import (
    insert_document,
    get_all_documents,
    get_documents_filtered,
    get_document_by_id,
    delete_document as db_delete_document,
    update_document_status,
)

# Document Agent pipeline (Durga's module).
# process_document() is synchronous and never raises — it returns a
# ProcessingResult with .success / .error.
from backend.document_agent.pipeline import process_document

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create API router
router = APIRouter(prefix="/api/documents", tags=["documents"])


# ============================================
# BACKGROUND TASK — pipeline worker
# ============================================

async def _run_pipeline(file_path: str, document_id: str, filename: str) -> None:
    """
    Background task: run the Document Agent pipeline for one document.

    Must be async so it runs INSIDE the FastAPI event loop (not in a
    threadpool).  This lets us `await` the async database calls directly.
    The sync process_document() call is offloaded via asyncio.to_thread()
    so it does not block the event loop.

    Status transitions:
        uploaded  ->  processing  (immediately before pipeline starts)
        processing -> indexed     (pipeline succeeded)
        processing -> failed      (pipeline returned success=False)
    """
    logger.info(f"[pipeline] Starting processing for {filename} (ID: {document_id})")

    # Mark as processing
    await update_document_status(document_id, "processing")

    # Run the sync pipeline in a thread so the event loop is not blocked.
    result = await asyncio.to_thread(
        process_document,
        file_path=file_path,
        document_id=document_id,
        metadata={},
    )

    if result.success:
        await update_document_status(document_id, "indexed")
        logger.info(
            f"[pipeline] Indexed {filename}: "
            f"{result.chunks_indexed} chunk(s). {result.message}"
        )
    else:
        await update_document_status(document_id, "failed")
        logger.error(
            f"[pipeline] Failed to process {filename}: {result.error}"
        )


# ============================================
# UPLOAD ENDPOINT
# ============================================

@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload a document (PDF, DOCX, or TXT).

    The endpoint:
      1. Validates file extension, size and MIME type.
      2. Saves the file to data/uploads/.
      3. Inserts a metadata row into documents.db with status='uploaded'.
      4. Returns HTTP 201 immediately.
      5. Runs the Document Agent pipeline as a background task; the
         document status updates to 'processing', then 'indexed' or 'failed'.

    Args:
        file: Uploaded file (multipart/form-data).

    Returns 201:
        {
            "status": "success",
            "message": "Document uploaded successfully",
            "document": {
                "document_id": "...",
                "filename": "report.pdf",
                "file_type": "PDF",
                "file_size": 1024000,
                "upload_date": "2024-01-15 10:30:00",
                "status": "uploaded"
            }
        }
    """
    try:
        logger.info(f"Upload request received: {file.filename}")

        # --- Step 1: read bytes ---
        file_content = await file.read()
        file_size = len(file_content)
        logger.info(f"File size: {file_size} bytes ({file_size / 1024:.2f} KB)")

        # --- Step 2: validate + save to disk ---
        result = await process_upload(
            file_content=file_content,
            filename=file.filename,
            file_size=file_size,
        )

        if not result.get("success"):
            error_message = result.get("error", "Upload processing failed")
            logger.error(f"Upload failed: {error_message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message,
            )

        document_id  = result["document_id"]
        filename     = result["filename"]
        file_type    = result["file_type"]
        file_size    = result["file_size"]
        file_path    = result["file_path"]
        upload_date  = result["upload_date"]

        # --- Step 3: insert DB record (status = 'uploaded') ---
        logger.info("Storing metadata in database...")
        db_success = await insert_document(
            document_id=document_id,
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            file_path=file_path,
            status="uploaded",
        )

        if not db_success:
            logger.error("Database insertion failed, cleaning up file...")
            delete_file(Path(file_path))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store document metadata. File removed.",
            )

        # --- Step 4: schedule background pipeline ---
        # The HTTP response is sent first; then _run_pipeline() fires.
        background_tasks.add_task(_run_pipeline, file_path, document_id, filename)
        logger.info(f"Pipeline queued for {filename} (ID: {document_id})")

        # --- Step 5: return 201 ---
        response_data = {
            "status": "success",
            "message": "Document uploaded successfully",
            "document": {
                "document_id": document_id,
                "filename": filename,
                "file_type": file_type,
                "file_size": file_size,
                "upload_date": upload_date,
                "status": "uploaded",   # pipeline will update this asynchronously
            },
        }

        logger.info(f"Upload complete: {filename} (ID: {document_id})")
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response_data,
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Unexpected error during upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e}",
        )


# ============================================
# LIST DOCUMENTS ENDPOINT
# ============================================

@router.get("/")
async def list_documents(
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by document status (uploaded, processing, indexed, failed)",
    ),
    file_type: Optional[str] = Query(
        default=None,
        description="Filter by file type (PDF, DOCX, TXT)",
    ),
    search: Optional[str] = Query(
        default=None,
        description="Case-insensitive substring search on filename",
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
            },
        )

    except Exception as e:
        logger.error(f"Failed to fetch documents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch documents: {e}",
        )


# ============================================
# GET DOCUMENT BY ID ENDPOINT
# ============================================

@router.get("/{document_id}")
async def get_document(document_id: str):
    """
    Get details of a specific document.

    Args:
        document_id: Unique document ID.
    """
    try:
        logger.info(f"Fetching document: {document_id}")
        document = await get_document_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {document_id}",
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "success", "document": document},
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to fetch document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch document: {e}",
        )


# ============================================
# DELETE DOCUMENT ENDPOINT
# ============================================

@router.delete("/{document_id}")
async def delete_document_endpoint(document_id: str):
    """
    Delete a document and its physical file.

    Args:
        document_id: Unique document ID.
    """
    try:
        logger.info(f"Deleting document: {document_id}")

        document = await get_document_by_id(document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {document_id}",
            )

        db_success = await db_delete_document(document_id)
        if not db_success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete document from database",
            )

        file_path = Path(document["file_path"])
        if file_path.exists():
            delete_file(file_path)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "message": f"Document deleted: {document['filename']}",
            },
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {e}",
        )
