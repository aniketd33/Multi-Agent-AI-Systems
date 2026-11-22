
"""
Documents API Endpoints
Handles document upload, listing, retrieval, deletion,
document indexing, and Red Flag Agent analysis.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    UploadFile,
    File,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import JSONResponse

from backend.services.upload import process_upload, delete_file

from backend.database import (
    insert_document,
    get_all_documents,
    get_documents_filtered,
    get_document_by_id,
    delete_document as db_delete_document,
)

from backend.database.db import (
    update_document_status,
    get_red_flag_analysis,
)

from backend.document_agent.pipeline import process_document
from backend.red_flag_agent.agent import run_red_flag_agent


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Create API router
router = APIRouter(
    prefix="/api/documents",
    tags=["documents"],
)


# ============================================================
# DOCUMENT PROCESSING + RED FLAG AGENT
# ============================================================

async def _run_pipeline(
    file_path: str,
    document_id: str,
    filename: str,
):
    """
    Background processing workflow:

    1. Update document status to processing.
    2. Run document indexing.
    3. Update document status to indexed.
    4. Run Red Flag Agent.
    5. Store Red Flag findings independently.

    Document indexing and Red Flag analysis have separate
    failure handling.
    """

    logger.info(
        "[pipeline] Starting processing for %s (ID: %s)",
        filename,
        document_id,
    )

    await update_document_status(document_id, "processing")

    try:
        # Document processing is synchronous, so run it
        # in a worker thread to avoid blocking FastAPI.
        result = await asyncio.to_thread(
            process_document,
            file_path=file_path,
            document_id=document_id,
            metadata={},
        )

        if not result.success:
            await update_document_status(document_id, "failed")

            logger.error(
                "[pipeline] Document processing failed: %s",
                result.error,
            )
            return

        # Mark document indexed before starting Red Flag analysis.
        await update_document_status(document_id, "indexed")

        logger.info(
            "[pipeline] Document indexed: %s. %s",
            filename,
            result.message,
        )

        # Run Red Flag Agent asynchronously.
        try:
            red_flag_result = await run_red_flag_agent(
                file_path=file_path,
                document_id=document_id,
                filename=filename,
            )

            logger.info(
                "[pipeline] Red Flag analysis completed for %s: %s findings",
                filename,
                red_flag_result["summary"]["total_findings"],
            )

        except Exception:
            # A Red Flag failure must not mark an indexed document failed.
            logger.exception(
                "[pipeline] Red Flag analysis failed for %s",
                filename,
            )

    except Exception:
        await update_document_status(document_id, "failed")

        logger.exception(
            "[pipeline] Document pipeline failed for %s",
            filename,
        )


# ============================================================
# UPLOAD DOCUMENT ENDPOINT
# ============================================================

@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload PDF, DOCX, or TXT documents.

    Workflow:
    1. Read uploaded file.
    2. Validate and save the file.
    3. Insert document metadata.
    4. Schedule document indexing and Red Flag analysis.
    5. Return upload response immediately.
    """

    try:
        logger.info(
            "[upload] Upload request received: %s",
            file.filename,
        )

        # Read uploaded file content.
        file_content = await file.read()
        file_size = len(file_content)

        logger.info(
            "[upload] File size: %s bytes",
            file_size,
        )

        # Validate and save uploaded file.
        result = await process_upload(
            file_content=file_content,
            filename=file.filename,
            file_size=file_size,
        )

        if not result.get("success"):
            error_message = result.get(
                "error",
                "Upload processing failed",
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message,
            )

        # Extract upload information.
        document_id = result["document_id"]
        filename = result["filename"]
        file_type = result["file_type"]
        file_size = result["file_size"]
        file_path = result["file_path"]
        upload_date = result["upload_date"]

        # Store document metadata.
        db_success = await insert_document(
            document_id=document_id,
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            file_path=file_path,
            status="uploaded",
        )

        if not db_success:
            logger.error(
                "[upload] Database insertion failed. Cleaning up file."
            )

            delete_file(Path(file_path))

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store document metadata. File removed.",
            )

        # Schedule indexing and Red Flag analysis.
        background_tasks.add_task(
            _run_pipeline,
            file_path,
            document_id,
            filename,
        )

        logger.info(
            "[upload] Upload successful: %s (ID: %s)",
            filename,
            document_id,
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "status": "success",
                "message": "Document uploaded successfully. AI analysis started in background.",
                "document": {
                    "document_id": document_id,
                    "filename": filename,
                    "file_type": file_type,
                    "file_size": file_size,
                    "upload_date": upload_date,
                    "status": "uploaded",
                },
            },
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("[upload] Unexpected upload error")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(exc)}",
        )

    finally:
        await file.close()


# ============================================================
# LIST DOCUMENTS ENDPOINT
# ============================================================

@router.get("/")
async def list_documents(
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by document status",
    ),
    file_type: Optional[str] = Query(
        default=None,
        description="Filter by file type (PDF, DOCX, TXT)",
    ),
    search: Optional[str] = Query(
        default=None,
        description="Case-insensitive filename search",
    ),
):
    """List uploaded documents with optional filters."""

    try:
        any_filter = (
            status_filter is not None
            or file_type is not None
            or search is not None
        )

        if any_filter:
            documents = await get_documents_filtered(
                status=status_filter,
                file_type=file_type,
                search=search,
            )
        else:
            documents = await get_all_documents()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "count": len(documents),
                "documents": documents,
            },
        )

    except Exception as exc:
        logger.exception("[documents] Failed to list documents")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch documents: {str(exc)}",
        )


# ============================================================
# GET DOCUMENT BY ID
# ============================================================

@router.get("/{document_id}")
async def get_document(document_id: str):
    """Retrieve a specific document by its ID."""

    try:
        document = await get_document_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {document_id}",
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "document": document,
            },
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("[documents] Failed to retrieve document")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch document: {str(exc)}",
        )



# ============================================================
# GET RED FLAG ANALYSIS
# ============================================================

@router.get("/{document_id}/red-flags")
async def get_document_red_flags(document_id: str):
    """
    Retrieve Red Flag Agent findings and calculate severity summary.
    """

    try:
        document = await get_document_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        analysis = await get_red_flag_analysis(document_id)

        if not analysis:
            return {
                "document_id": document_id,
                "filename": document["filename"],
                "status": "pending",
                "summary": {
                    "total_findings": 0,
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                },
                "findings": [],
                "message": "Red Flag analysis has not completed yet.",
            }

        findings = analysis.get("findings", [])

        if not isinstance(findings, list):
            findings = []

        # Calculate severity counts from saved findings.
        severity_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }

        for finding in findings:
            if not isinstance(finding, dict):
                continue

            severity = str(
                finding.get("severity", "low")
            ).strip().lower()

            if severity in severity_counts:
                severity_counts[severity] += 1

        summary = {
            "total_findings": len(findings),
            **severity_counts,
        }

        return {
            "document_id": document_id,
            "filename": document["filename"],
            **analysis,
            "summary": summary,
            "findings": findings,
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "[red-flags] Failed to retrieve analysis"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve Red Flag analysis.",
        )


# ============================================================
# DELETE DOCUMENT ENDPOINT
# ============================================================

@router.delete("/{document_id}")
async def delete_document_endpoint(document_id: str):
    """Delete a document and its database record."""

    try:
        document = await get_document_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {document_id}",
            )

        # Delete metadata from database.
        db_success = await db_delete_document(document_id)

        if not db_success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete document from database",
            )

        # Delete the physical file.
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

    except Exception as exc:
        logger.exception("[documents] Failed to delete document")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(exc)}",
        )
