import sys
import io

from typing import BinaryIO, Any


from .._base_converter import DocumentConverter, DocumentConverterResult
from .._stream_info import StreamInfo
from .._exceptions import MissingDependencyException, MISSING_DEPENDENCY_MESSAGE


# Try loading optional (but in this case, required) dependencies
# Save reporting of any exceptions for later
_dependency_exc_info = None
try:
    import pdfminer
    import pdfminer.high_level
    import pdfminer.layout
    import pdfminer.pdfinterp
    import pdfminer.pdfpage
    import pdfminer.converter
    import pdfminer.psparser
    import pdfminer.pdfparser
except ImportError:
    # Preserve the error and stack trace for later
    _dependency_exc_info = sys.exc_info()


ACCEPTED_MIME_TYPE_PREFIXES = [
    "application/pdf",
    "application/x-pdf",
]

ACCEPTED_FILE_EXTENSIONS = [".pdf"]


class PdfConverter(DocumentConverter):
    """
    Converts PDFs to Markdown. Most style information is ignored, so the results are essentially plain-text.
    """

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,  # Options to pass to the converter
    ) -> bool:
        mimetype = (stream_info.mimetype or "").lower()
        extension = (stream_info.extension or "").lower()

        if extension in ACCEPTED_FILE_EXTENSIONS:
            return True

        for prefix in ACCEPTED_MIME_TYPE_PREFIXES:
            if mimetype.startswith(prefix):
                return True

        return False

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,  # Options to pass to the converter
    ) -> DocumentConverterResult:
        # Check the dependencies
        if _dependency_exc_info is not None:
            raise MissingDependencyException(
                MISSING_DEPENDENCY_MESSAGE.format(
                    converter=type(self).__name__,
                    extension=".pdf",
                    feature="pdf",
                )
            ) from _dependency_exc_info[
                1
            ].with_traceback(  # type: ignore[union-attr]
                _dependency_exc_info[2]
            )

        assert isinstance(file_stream, io.IOBase)  # for mypy
        
        # Check if page separators are requested
        add_page_separators = kwargs.get("add_page_separators", False)
        
        if add_page_separators:
            return self._convert_with_page_separators(file_stream)
        else:
            return DocumentConverterResult(
                markdown=pdfminer.high_level.extract_text(file_stream),
            )

    def _convert_with_page_separators(self, file_stream: BinaryIO) -> DocumentConverterResult:
        """
        Convert PDF to markdown with page separators between each page.
        Optimized for efficiency with large PDFs.
        """
        # Reset file stream position
        file_stream.seek(0)
        
        # Create PDF parser and document
        parser = pdfminer.pdfparser.PDFParser(file_stream)
        doc = pdfminer.pdfpage.PDFDocument(parser)
        
        # Create resource manager and device (reused for all pages)
        rsrcmgr = pdfminer.pdfinterp.PDFResourceManager()
        
        # Pre-define layout parameters (reused for all pages)
        laparams = pdfminer.layout.LAParams()
        
        # Use a single string buffer and device for all pages
        retstr = io.StringIO()
        device = pdfminer.converter.TextConverter(rsrcmgr, retstr, laparams=laparams)
        
        # Use a list for efficient string building
        result_parts = []
        first_page = True
        
        try:
            for page in pdfminer.pdfpage.PDFPage.create_pages(doc):
                # Clear the buffer for the new page
                retstr.seek(0)
                retstr.truncate(0)
                
                # Process the page
                pdfminer.pdfinterp.PDFPageInterpreter(rsrcmgr, device).process_page(page)
                
                # Get the text content
                page_text = retstr.getvalue().strip()
                
                # Add page separator if this is not the first page and page has content
                if not first_page and page_text:
                    result_parts.append("\n\n---\n\n")
                
                # Add page content
                if page_text:
                    result_parts.append(page_text)
                
                first_page = False
        
        finally:
            # Clean up resources
            device.close()
            retstr.close()
        
        # Combine all parts efficiently
        full_text = "".join(result_parts)
        
        return DocumentConverterResult(markdown=full_text)
