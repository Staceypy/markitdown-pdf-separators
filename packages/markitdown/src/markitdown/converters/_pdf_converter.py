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

# Try loading PyMuPDF for header/footer removal
_pymupdf_dependency_exc_info = None
try:
    import fitz  # PyMuPDF
except ImportError:
    # Preserve the error and stack trace for later
    _pymupdf_dependency_exc_info = sys.exc_info()


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
        remove_headers_footers = kwargs.get("remove_headers_footers", False)
        
        if add_page_separators or remove_headers_footers:
            return self._convert_with_options(file_stream, add_page_separators, remove_headers_footers)
        else:
            return DocumentConverterResult(
                markdown=pdfminer.high_level.extract_text(file_stream),
            )

    def _convert_with_options(self, file_stream: BinaryIO, add_page_separators: bool, remove_headers_footers: bool) -> DocumentConverterResult:
        """
        Convert PDF to markdown with optional page separators and header/footer removal.
        """
        # Reset file stream position
        file_stream.seek(0)
        
        # If header/footer removal is requested, check PyMuPDF dependency
        if remove_headers_footers and _pymupdf_dependency_exc_info is not None:
            raise MissingDependencyException(
                MISSING_DEPENDENCY_MESSAGE.format(
                    converter=type(self).__name__,
                    extension=".pdf",
                    feature="pymupdf",
                )
            ) from _pymupdf_dependency_exc_info[
                1
            ].with_traceback(  # type: ignore[union-attr]
                _pymupdf_dependency_exc_info[2]
            )
        
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
        
        # Remove headers and footers if requested (after combining all pages)
        if remove_headers_footers and full_text:
            removed_headers_footers_full_text = self._remove_headers_footers_from_text(full_text)
        else:
            removed_headers_footers_full_text = full_text
        
        return DocumentConverterResult(markdown=removed_headers_footers_full_text)

    def _remove_headers_footers_from_text(self, text: str) -> str:
        """
        Remove headers and footers from text using intelligent pattern detection:
        1. Collect all last lines above page separators
        2. Find duplicates and remove all occurrences
        3. Extract common patterns from remaining lines and remove them
        """
        print("DEBUG: _remove_headers_footers_from_text called!")
        
        # Split by page separators to get individual pages
        pages = text.split('\n\n---\n\n')
        
        if len(pages) <= 1:  # No page separators, use simple approach
            return self._remove_headers_footers_simple(text)
        
        # Collect the last 2 non-empty lines of each page (before the separator)
        last_lines = []
        # Collect the first 2 non-empty lines of each page (after the separator)
        first_lines = []
        for page in pages:
            page = page.strip()
            if page:
                lines = page.split('\n')
                # Find the last 2 non-empty lines
                found_lines = []
                for line in reversed(lines):
                    candidate = line.strip()
                    if candidate:
                        found_lines.append(candidate)
                        if len(found_lines) >= 2:  # Stop after finding 2 lines
                            break
                last_lines.extend(found_lines)
                
                # Find the first 2 non-empty lines
                found_first_lines = []
                for line in lines:
                    candidate = line.strip()
                    if candidate:
                        found_first_lines.append(candidate)
                        if len(found_first_lines) >= 2:  # Stop after finding 2 lines
                            break
                first_lines.extend(found_first_lines)
        
        # Debug output
        print(f"DEBUG: Found {len(last_lines)} last lines from {len(pages)} pages")
        if last_lines:
            print("DEBUG: First 5 last lines:", last_lines[:5])
        
        print(f"DEBUG: Found {len(first_lines)} first lines from {len(pages)} pages")
        if first_lines:
            print("DEBUG: First 5 first lines:", first_lines[:5])
        
        if len(last_lines) <= 1 and len(first_lines) <= 1:  # Not enough lines to detect patterns
            print("DEBUG: Not enough lines to detect patterns")
            return text
        
        # Find lines that appear more than once (duplicates) - from both first and last lines
        from collections import Counter
        all_lines = last_lines + first_lines
        line_counts = Counter(all_lines)
        duplicate_lines = {line for line, count in line_counts.items() if count > 1}
        
        print(f"DEBUG: Found {len(duplicate_lines)} duplicate lines")
        if duplicate_lines:
            print("DEBUG: Duplicate lines:", list(duplicate_lines)[:3])
            # Show how many times each duplicate appears
            for line in list(duplicate_lines)[:3]:
                print(f"DEBUG: '{line}' appears {line_counts[line]} times")
        
        # Get remaining lines after removing duplicates
        remaining_last_lines = [line for line in last_lines if line not in duplicate_lines]
        remaining_first_lines = [line for line in first_lines if line not in duplicate_lines]
        
        print(f"DEBUG: {len(remaining_last_lines)} last lines remaining after removing duplicates")
        print(f"DEBUG: {len(remaining_first_lines)} first lines remaining after removing duplicates")
        
        # Find common patterns in remaining lines
        pattern_lines = self._find_common_patterns(remaining_last_lines + remaining_first_lines)
        
        print(f"DEBUG: Found {len(pattern_lines)} pattern lines")
        if pattern_lines:
            print("DEBUG: Pattern lines first 3:", list(pattern_lines)[:3])
            # Show how many times each pattern appears
            for line in list(pattern_lines)[:3]:
                print(f"DEBUG: '{line}' appears {line_counts[line]} times")
        
        # Combine all lines to remove
        lines_to_remove = duplicate_lines | pattern_lines
        
        print(f"DEBUG: Total unique lines to remove: {len(lines_to_remove)}")
        # Calculate total lines being removed (counting all occurrences)
        total_removals = sum(line_counts[line] for line in lines_to_remove)
        print(f"DEBUG: Total lines being removed (all occurrences): {total_removals}")
        
        # Remove these lines from all pages
        cleaned_pages = []
        for page in pages:
            page = page.strip()
            if page:
                lines = page.split('\n')
                
                # Find and remove up to 2 lines from the beginning if they're in our removal list
                lines_removed_from_start = 0
                for i in range(len(lines)):
                    candidate = lines[i].strip()
                    print(f"DEBUG: start candidate: {candidate}")
                    if candidate and candidate in lines_to_remove and lines_removed_from_start < 2:
                        print(f"DEBUG: removing start line: {candidate}")
                        lines = lines[i+1:]  # Remove this line and everything before it
                        lines_removed_from_start += 1
                        print(f"DEBUG: start lines removed so far: {lines_removed_from_start}")
                        if lines_removed_from_start >= 2:  # Stop after removing 2 lines
                            break
                    elif candidate:
                        print(f"DEBUG: start line not in lines_to_remove: {candidate}")
                        break  # Stop at first non-empty line that's not in removal list
                
                # Find and remove up to 2 lines from the end if they're in our removal list
                lines_removed_from_end = 0
                for i in range(len(lines) - 1, -1, -1):
                    candidate = lines[i].strip()
                    print(f"DEBUG: end candidate: {candidate}")
                    if candidate and candidate in lines_to_remove and lines_removed_from_end < 2:
                        print(f"DEBUG: removing end line: {candidate}")
                        lines = lines[:i]  # Remove this line and everything after it
                        lines_removed_from_end += 1
                        print(f"DEBUG: end lines removed so far: {lines_removed_from_end}")
                        if lines_removed_from_end >= 2:  # Stop after removing 2 lines
                            break
                    elif candidate:
                        print(f"DEBUG: end line not in lines_to_remove: {candidate}")
                
                cleaned_pages.append('\n'.join(lines))
        
        # Rejoin with page separators
        return '\n\n---\n\n'.join(cleaned_pages)

    def _find_common_patterns(self, lines: list) -> set:
        """
        Find common patterns in a list of lines using simple pattern matching.
        Focuses on page numbers and similar repetitive content.
        """
        if len(lines) < 2:
            return set()
        
        import re
        
        # Convert lines to lowercase for pattern matching
        lines_lower = [line.lower() for line in lines]
        
        pattern_lines = set()
        
        # Strategy 1: Find lines that contain numbers and share common words
        for i, line in enumerate(lines_lower):
            # Check if line contains numbers
            if not re.search(r'\d', line):
                continue
                
            words = set(re.findall(r'\b\w+\b', line))
            if len(words) == 0:
                continue
                
            # Count how many other lines share words with this line
            shared_count = 0
            for j, other_line in enumerate(lines_lower):
                if i != j:
                    other_words = set(re.findall(r'\b\w+\b', other_line))
                    if words & other_words:  # Intersection
                        shared_count += 1
            
            # If this line shares words with at least one other line, it's likely a pattern
            if shared_count >= 1:
                pattern_lines.add(lines[i])
        
        # Strategy 2: Find lines with similar structure (like "16/284", "18/284")
        for i, line in enumerate(lines):
            # Create a structure pattern: replace numbers with 'N', keep other chars
            structure = re.sub(r'\d+', 'N', line)
            
            # Count how many other lines have the same structure
            structure_count = 0
            for j, other_line in enumerate(lines):
                if i != j:
                    other_structure = re.sub(r'\d+', 'N', other_line)
                    if structure == other_structure:
                        structure_count += 1
            
            # If this line has the same structure as at least one other line, it's likely a pattern
            if structure_count >= 1:
                pattern_lines.add(lines[i])
        
        # Strategy 3: Find lines that are exactly the same (duplicates that weren't caught)
        for i, line in enumerate(lines):
            for j, other_line in enumerate(lines):
                if i != j and line == other_line:
                    pattern_lines.add(lines[i])
                    break
        
        return pattern_lines

    def _lines_share_structure(self, lines: list) -> bool:
        """
        Check if lines share similar character structure (e.g., same punctuation, similar character types).
        """
        if len(lines) < 2:
            return False
        
        # Check if lines have similar character patterns
        patterns = []
        for line in lines:
            # Create a pattern of character types (letter, digit, space, punctuation)
            pattern = []
            for char in line:
                if char.isalpha():
                    pattern.append('L')
                elif char.isdigit():
                    pattern.append('D')
                elif char.isspace():
                    pattern.append('S')
                else:
                    pattern.append('P')
            patterns.append(''.join(pattern))
        
        # Check if patterns are similar (at least 70% similarity)
        if len(patterns) >= 2:
            base_pattern = patterns[0]
            for pattern in patterns[1:]:
                # Calculate similarity
                min_len = min(len(base_pattern), len(pattern))
                if min_len == 0:
                    continue
                matches = sum(1 for i in range(min_len) if base_pattern[i] == pattern[i])
                similarity = matches / min_len
                if similarity >= 0.7:  # 70% similarity threshold
                    return True
        
        return False

    def _remove_headers_footers_simple(self, text: str) -> str:
        """
        Simple header/footer removal for documents without page separators.
        This is the original logic for backward compatibility.
        """
        lines = text.split('\n')
        if len(lines) <= 4:  # Very short pages, don't remove anything
            return text
        
        # Remove common header patterns (first 1-2 lines)
        header_lines_to_remove = 0
        for i in range(min(2, len(lines))):
            line = lines[i].strip()
            # Check for common header patterns
            if (line.isdigit() or  # Page numbers
                len(line) < 20 or  # Very short lines
                line.lower() in ['page', 'page of', 'confidential', 'draft', 'final'] or
                any(word in line.lower() for word in ['copyright', 'all rights reserved', 'proprietary'])):
                header_lines_to_remove = i + 1
        
        # Remove common footer patterns (last 1-2 lines)
        footer_lines_to_remove = 0
        for i in range(min(2, len(lines))):
            line = lines[-(i+1)].strip()
            # Check for common footer patterns
            if (line.isdigit() or  # Page numbers
                len(line) < 20 or  # Very short lines
                line.lower() in ['page', 'page of', 'confidential', 'draft', 'final'] or
                any(word in line.lower() for word in ['copyright', 'all rights reserved', 'proprietary'])):
                footer_lines_to_remove = i + 1
        
        # Remove the identified header and footer lines
        if header_lines_to_remove > 0:
            lines = lines[header_lines_to_remove:]
        if footer_lines_to_remove > 0:
            lines = lines[:-footer_lines_to_remove]
        
        return '\n'.join(lines)

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
