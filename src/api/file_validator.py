import os
import re
import hashlib
import logging
import requests
import zipfile
import io
from typing import Optional, NamedTuple
from fastapi import UploadFile

# Audit logger streams
audit_logger = logging.getLogger("rag_system.audit.file_validator")
logger = logging.getLogger("rag_system.api.file_validator")

class ValidationResult(NamedTuple):
    valid: bool
    rejection_reason: Optional[str]
    file_type: str
    size_bytes: int

class FileValidator:
    """Validates uploaded or local files to protect the system from size exhaustion, script injection, and zip bombs."""

    def __init__(self, max_size_mb: float = 10.0) -> None:
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)

    def validate(self, upload_file: UploadFile) -> ValidationResult:
        logger.info(f"Starting security validation check for UploadFile: {upload_file.filename}")
        try:
            # Measure actual file length
            upload_file.file.seek(0, os.SEEK_END)
            size_bytes = upload_file.file.tell()
            upload_file.file.seek(0)
        except Exception as e:
            logger.error(f"Failed to inspect file size: {str(e)}")
            return ValidationResult(False, "Failed to read file size metrics.", "unknown", 0)

        if size_bytes > self.max_size_bytes:
            audit_logger.warning(
                f"Security Block: Uploaded file '{upload_file.filename}' size ({size_bytes} bytes) exceeds limit ({self.max_size_bytes} bytes)."
            )
            return ValidationResult(False, f"File size exceeds maximum allowed limit of {self.max_size_bytes // (1024 * 1024)}MB.", "unknown", size_bytes)

        # Read magic bytes
        try:
            magic_bytes = upload_file.file.read(8)
            upload_file.file.seek(0)
        except Exception as e:
            logger.error(f"Failed to read magic bytes: {str(e)}")
            return ValidationResult(False, "Failed to inspect file headers.", "unknown", size_bytes)

        ext = os.path.splitext(upload_file.filename or "")[1].lower()
        return self._run_security_scans(upload_file.filename, ext, magic_bytes, upload_file.file.read, size_bytes)

    def validate_filepath(self, file_path: str) -> ValidationResult:
        logger.info(f"Starting security validation check for file path: {file_path}")
        if not os.path.exists(file_path):
            return ValidationResult(False, "File does not exist.", "unknown", 0)

        try:
            size_bytes = os.path.getsize(file_path)
        except Exception as e:
            logger.error(f"Failed to inspect local file size: {str(e)}")
            return ValidationResult(False, "Failed to read local file size metrics.", "unknown", 0)

        if size_bytes > self.max_size_bytes:
            audit_logger.warning(
                f"Security Block: Local file '{file_path}' size ({size_bytes} bytes) exceeds limit ({self.max_size_bytes} bytes)."
            )
            return ValidationResult(False, f"File size exceeds maximum allowed limit of {self.max_size_bytes // (1024 * 1024)}MB.", "unknown", size_bytes)

        try:
            with open(file_path, "rb") as f:
                magic_bytes = f.read(8)
        except Exception as e:
            logger.error(f"Failed to read local magic bytes: {str(e)}")
            return ValidationResult(False, "Failed to inspect local file headers.", "unknown", size_bytes)

        ext = os.path.splitext(file_path)[1].lower()

        def read_content():
            with open(file_path, "rb") as f:
                return f.read()

        return self._run_security_scans(os.path.basename(file_path), ext, magic_bytes, read_content, size_bytes)

    def _run_security_scans(self, filename: str, ext: str, magic_bytes: bytes, read_fn, size_bytes: int) -> ValidationResult:
        # Magic bytes extension check
        if ext == ".pdf":
            if not magic_bytes.startswith(b"%PDF-"):
                audit_logger.warning(
                    f"Security Block: PDF magic bytes verification failed for '{filename}'."
                )
                return ValidationResult(False, "Invalid PDF file header structure.", "pdf", size_bytes)
            file_type = "pdf"
        elif ext == ".docx":
            if not magic_bytes.startswith(b"PK\x03\x04"):
                audit_logger.warning(
                    f"Security Block: DOCX magic bytes verification failed for '{filename}'."
                )
                return ValidationResult(False, "Invalid DOCX file header structure.", "docx", size_bytes)
            file_type = "docx"
        elif ext in [".md", ".txt"]:
            try:
                # Read content sample and try to decode as UTF-8
                content_sample = read_fn()[:1024]
                content_sample.decode("utf-8")
            except UnicodeDecodeError:
                audit_logger.warning(
                    f"Security Block: Text file verification failed for '{filename}' (not valid UTF-8)."
                )
                return ValidationResult(False, "Invalid file encoding: Text files must be valid UTF-8.", "text", size_bytes)
            file_type = "text"
        else:
            file_type = "unsupported"
            return ValidationResult(False, f"Unsupported file extension '{ext}'. Only .pdf, .docx, .md, and .txt are supported.", file_type, size_bytes)

        # Content scanning for scripts
        try:
            content = read_fn()
        except Exception as e:
            logger.error(f"Failed to read file contents for script scanning: {str(e)}")
            return ValidationResult(False, "Failed to scan file content.", file_type, size_bytes)

        # Zip bomb check for docx compressed data
        if file_type == "docx":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    total_uncompressed = 0
                    for info in zf.infolist():
                        total_uncompressed += info.file_size
                    if size_bytes > 0:
                        ratio = total_uncompressed / size_bytes
                        if ratio > 100:
                            audit_logger.warning(
                                f"Security Block: Zip bomb detected in file '{filename}'! Ratio: {ratio:.1f}:1"
                            )
                            return ValidationResult(False, "File rejected: Zip bomb detected (compression ratio exceeds 100:1).", file_type, size_bytes)
            except Exception as e:
                audit_logger.warning(f"Failed to inspect zip compression for '{filename}': {str(e)}")
                return ValidationResult(False, "Failed to verify archive integrity.", file_type, size_bytes)

        if file_type == "pdf":
            content_str = content.decode("utf-8", errors="ignore")
            # PDF JavaScript trigger keywords: /JS, /JavaScript
            if re.search(r"/\s*JS\b", content_str, re.IGNORECASE) or re.search(r"/\s*JavaScript\b", content_str, re.IGNORECASE):
                audit_logger.warning(
                    f"Security Block: Unauthorized JavaScript detected in PDF '{filename}'!"
                )
                return ValidationResult(False, "File contains unauthorized scripts or executable code.", file_type, size_bytes)

            # Executable instructions (/Launch or /EmbeddedFile)
            if re.search(r"/\s*Launch\b", content_str, re.IGNORECASE) or re.search(r"/\s*EmbeddedFile\b", content_str, re.IGNORECASE):
                audit_logger.warning(
                    f"Security Block: Executable actions found in PDF '{filename}'!"
                )
                return ValidationResult(False, "File contains unauthorized executable attachments.", file_type, size_bytes)

        # Optional malware hash check via VirusTotal API
        vt_api_key = os.environ.get("VIRUSTOTAL_API_KEY")
        if vt_api_key:
            file_hash = hashlib.sha256(content).hexdigest()
            logger.info(f"Submitting file hash {file_hash} to VirusTotal...")
            try:
                url = f"https://www.virustotal.com/api/v3/files/{file_hash}"
                headers = {"x-apikey": vt_api_key}
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    vt_data = response.json()
                    stats = vt_data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                    malicious = stats.get("malicious", 0)
                    suspicious = stats.get("suspicious", 0)
                    if malicious > 0 or suspicious > 0:
                        audit_logger.critical(
                            f"Security Block: VirusTotal flagged file '{filename}' as suspicious! Stats: {stats}"
                        )
                        return ValidationResult(False, "Malware check failed: File flagged as malicious.", file_type, size_bytes)
                elif response.status_code == 404:
                    logger.info("File hash not found in VirusTotal database; proceeding as clean.")
                else:
                    logger.warning(f"VirusTotal hash lookup returned status: {response.status_code}")
            except Exception as e:
                logger.warning(f"VirusTotal API lookup failed: {str(e)}")

        return ValidationResult(True, None, file_type, size_bytes)
