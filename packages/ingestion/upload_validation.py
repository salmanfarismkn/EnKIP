from io import BytesIO

from pypdf import PdfReader


SUPPORTED_UPLOAD_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "application/pdf",
}


class UploadValidationError(ValueError):
    pass


def validate_upload_content(
    content: bytes,
    mime_type: str,
    *,
    max_pdf_pages: int,
) -> None:
    if not content:
        raise UploadValidationError("Uploaded file is empty")

    if mime_type not in SUPPORTED_UPLOAD_MIME_TYPES:
        raise UploadValidationError(
            "Unsupported file type; supported types are text/plain, "
            "text/markdown, and application/pdf"
        )

    if mime_type == "application/pdf":
        if not content.startswith(b"%PDF-"):
            raise UploadValidationError("File is not a valid PDF document")
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise UploadValidationError("Encrypted PDF documents are not supported")
            page_count = len(reader.pages)
        except UploadValidationError:
            raise
        except Exception as exc:
            raise UploadValidationError("File is a malformed PDF document") from exc
        if page_count == 0:
            raise UploadValidationError("PDF document contains no pages")
        if page_count > max_pdf_pages:
            raise UploadValidationError(
                f"PDF document exceeds the {max_pdf_pages}-page limit"
            )
        return

    if b"\x00" in content:
        raise UploadValidationError("File content does not match text/plain or text/markdown")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadValidationError("Text document must be valid UTF-8") from exc
