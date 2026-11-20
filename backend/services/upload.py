"""
Upload Service Module
Handles file upload, validation, and storage operations
Multi-Agent AI System for Finance and Business Insights
Developer: Aniket - Document Intelligence Agent Module
"""

import os
import uuid
import magic
import shutil
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Upload directory
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"

# Maximum file size (20 MB)
# Maximum file size (100 MB)
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB in bytes

# Allowed file extensions
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# MIME type mappings for validation
MIME_TYPE_MAPPINGS = {
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
    "application/msword": "DOC",  # Older Word format
    "application/zip": "DOCX",         # DOCX files are ZIP archives; libmagic may return this
    "text/plain": "TXT",
}

# ============================================
# INITIALIZATION
# ============================================

def initialize_upload_directory():
    """
    Ensure upload directory exists
    """
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ Upload directory ready: {UPLOAD_DIR}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create upload directory: {e}")
        return False

# ============================================
# VALIDATION FUNCTIONS
# ============================================

def validate_file_extension(filename: str) -> Tuple[bool, Optional[str]]:
    """
    Validate file extension
    
    Args:
        filename: Original filename
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    file_ext = Path(filename).suffix.lower()
    
    if not file_ext:
        return False, "File has no extension"
    
    if file_ext not in ALLOWED_EXTENSIONS:
        return False, f"File type '{file_ext}' not allowed. Allowed types: PDF, DOCX, TXT"
    
    return True, None


def validate_file_size(file_size: int) -> Tuple[bool, Optional[str]]:
    """
    Validate file size
    
    Args:
        file_size: File size in bytes
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if file_size == 0:
        return False, "File is empty (0 bytes)"
    
    if file_size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        actual_mb = file_size / (1024 * 1024)
        return False, f"File too large ({actual_mb:.2f} MB). Maximum allowed: {max_mb:.0f} MB"
    
    return True, None


def validate_file_content(file_path: Path) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate actual file content using python-magic
    
    Args:
        file_path: Path to the file
        
    Returns:
        Tuple[bool, Optional[str], Optional[str]]: (is_valid, error_message, detected_type)
    """
    try:
        # Detect MIME type
        mime = magic.Magic(mime=True)
        detected_mime = mime.from_file(str(file_path))
        
        logger.info(f"Detected MIME type: {detected_mime}")
        
        # Check if detected type is allowed
        if detected_mime in MIME_TYPE_MAPPINGS:
            file_type = MIME_TYPE_MAPPINGS[detected_mime]
            return True, None, file_type
        
        # Special case for text files (can have various MIME types)
        if detected_mime.startswith("text/"):
            return True, None, "TXT"
        
        return False, f"File content type '{detected_mime}' not allowed", None
        
    except Exception as e:
        logger.warning(f"Content validation failed: {e}")
        # If python-magic fails, fall back to extension-based validation
        return True, None, None


# ============================================
# FILE OPERATIONS
# ============================================

def generate_unique_filename(original_filename: str, document_id: str) -> str:
    """
    Generate a unique filename to prevent conflicts
    
    Args:
        original_filename: Original uploaded filename
        document_id: Unique document ID (UUID)
        
    Returns:
        str: Unique filename like "uuid_originalname.ext"
        
    Example:
        "123e4567_report.pdf"
    """
    # Get file extension
    file_ext = Path(original_filename).suffix
    
    # Get filename without extension
    base_name = Path(original_filename).stem
    
    # Create safe filename (remove special characters)
    safe_base = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in base_name)
    
    # Combine: uuid_filename.ext
    unique_filename = f"{document_id}_{safe_base}{file_ext}"
    
    return unique_filename


def save_uploaded_file(file_content: bytes, filename: str) -> Tuple[bool, Optional[Path], Optional[str]]:
    """
    Save uploaded file to upload directory
    
    Args:
        file_content: File content as bytes
        filename: Filename to save as
        
    Returns:
        Tuple[bool, Optional[Path], Optional[str]]: (success, file_path, error_message)
    """
    try:
        # Ensure upload directory exists
        initialize_upload_directory()
        
        # Full file path
        file_path = UPLOAD_DIR / filename
        
        # Write file
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        logger.info(f"✅ File saved: {file_path}")
        return True, file_path, None
        
    except Exception as e:
        logger.error(f"❌ Failed to save file: {e}")
        return False, None, f"Failed to save file: {str(e)}"


def delete_file(file_path: Path) -> bool:
    """
    Delete a file (used for cleanup on errors)
    
    Args:
        file_path: Path to file to delete
        
    Returns:
        bool: True if successful
    """
    try:
        if file_path.exists():
            file_path.unlink()
            logger.info(f"✅ File deleted: {file_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Failed to delete file: {e}")
        return False


# ============================================
# MAIN UPLOAD FUNCTION
# ============================================

async def process_upload(
    file_content: bytes,
    filename: str,
    file_size: int
) -> dict:
    """
    Process file upload with complete validation and storage
    
    This is the main function that:
    1. Validates file extension
    2. Validates file size
    3. Generates unique document ID
    4. Saves file to disk
    5. Validates file content
    6. Returns document information
    
    Args:
        file_content: File content as bytes
        filename: Original filename
        file_size: File size in bytes
        
    Returns:
        dict: Result with success status, document info, or error
        
    Example Success:
        {
            "success": True,
            "document_id": "123e4567-e89b-12d3-a456-426614174000",
            "filename": "report.pdf",
            "file_type": "PDF",
            "file_size": 1024000,
            "file_path": "/path/to/uploads/123e4567_report.pdf",
            "stored_filename": "123e4567_report.pdf"
        }
        
    Example Error:
        {
            "success": False,
            "error": f"File too large ({actual_mb:.2f} MB). Maximum allowed: 100 MB"
        }
    """
    
    # Step 1: Validate file extension
    is_valid, error = validate_file_extension(filename)
    if not is_valid:
        logger.warning(f"⚠️  Extension validation failed: {error}")
        return {"success": False, "error": error}
    
    # Step 2: Validate file size
    is_valid, error = validate_file_size(file_size)
    if not is_valid:
        logger.warning(f"⚠️  Size validation failed: {error}")
        return {"success": False, "error": error}
    
    # Step 3: Generate unique document ID
    document_id = str(uuid.uuid4())
    logger.info(f"Generated document ID: {document_id}")
    
    # Step 4: Generate unique filename
    unique_filename = generate_unique_filename(filename, document_id)
    logger.info(f"Unique filename: {unique_filename}")
    
    # Step 5: Save file to disk
    success, file_path, error = save_uploaded_file(file_content, unique_filename)
    if not success:
        return {"success": False, "error": error}
    
    # Step 6: Validate file content
    is_valid, error, detected_type = validate_file_content(file_path)
    if not is_valid:
        # Delete the file if content validation fails
        delete_file(file_path)
        logger.warning(f"⚠️  Content validation failed: {error}")
        return {"success": False, "error": error}
    
    # Step 7: Determine file type
    # Use detected type if available, otherwise use extension
    if detected_type:
        file_type = detected_type
    else:
        file_type = Path(filename).suffix.upper().replace(".", "")
    
    # Step 8: Return success result
    result = {
        "success": True,
        "document_id": document_id,
        "filename": filename,  # Original filename
        "stored_filename": unique_filename,  # Unique stored filename
        "file_type": file_type,
        "file_size": file_size,
        "file_path": str(file_path),
        "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    logger.info(f"✅ Upload processed successfully: {filename}")
    return result


# ============================================
# UTILITY FUNCTIONS
# ============================================

def get_upload_directory() -> Path:
    """Get the upload directory path"""
    return UPLOAD_DIR


def format_file_size(size_bytes: int) -> str:
    """
    Format file size for display
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        str: Formatted size (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


# Initialize upload directory on module import
initialize_upload_directory()
