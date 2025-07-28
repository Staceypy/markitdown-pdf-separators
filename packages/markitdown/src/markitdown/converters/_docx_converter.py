import sys
import re
import zipfile
from io import BytesIO
from typing import BinaryIO, Any, List

from ._html_converter import HtmlConverter
from ..converter_utils.docx.pre_process import pre_process_docx
from .._base_converter import DocumentConverterResult
from .._stream_info import StreamInfo
from .._exceptions import MissingDependencyException, MISSING_DEPENDENCY_MESSAGE

# Try loading optional (but in this case, required) dependencies
# Save reporting of any exceptions for later
_dependency_exc_info = None
try:
    import mammoth
except ImportError:
    # Preserve the error and stack trace for later
    _dependency_exc_info = sys.exc_info()


ACCEPTED_MIME_TYPE_PREFIXES = [
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]

ACCEPTED_FILE_EXTENSIONS = [".docx"]


class DocxConverter(HtmlConverter):
    """
    Converts DOCX files to Markdown. Style information (e.g.m headings) and tables are preserved where possible.
    """

    def __init__(self):
        super().__init__()
        self._html_converter = HtmlConverter()

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
        # Check: the dependencies
        if _dependency_exc_info is not None:
            raise MissingDependencyException(
                MISSING_DEPENDENCY_MESSAGE.format(
                    converter=type(self).__name__,
                    extension=".docx",
                    feature="docx",
                )
            ) from _dependency_exc_info[
                1
            ].with_traceback(  # type: ignore[union-attr]
                _dependency_exc_info[2]
            )

        # Check if page separators or header/footer removal are requested
        add_page_separators = kwargs.get("add_page_separators", False)
        remove_headers_footers = kwargs.get("remove_headers_footers", False)
        
        if add_page_separators or remove_headers_footers:
            return self._convert_with_options(file_stream, add_page_separators, remove_headers_footers)
        else:
            # Original conversion logic
            style_map = kwargs.get("style_map", None)
            pre_process_stream = pre_process_docx(file_stream)
            return self._html_converter.convert_string(
                mammoth.convert_to_html(pre_process_stream, style_map=style_map).value,
                **kwargs,
            )

    def _convert_with_options(self, file_stream: BinaryIO, add_page_separators: bool, remove_headers_footers: bool) -> DocumentConverterResult:
        """
        Convert DOCX to markdown with optional page separators and header/footer removal.
        """
        # Reset file stream position
        file_stream.seek(0)
        
        # Pre-process the DOCX file
        pre_process_stream = pre_process_docx(file_stream)
        
        # Extract page information if needed
        pages = []
        if add_page_separators:
            pages = self._extract_pages_from_docx(pre_process_stream)
        else:
            # Convert normally without page separation
            html_content = mammoth.convert_to_html(pre_process_stream).value
            result = self._html_converter.convert_string(html_content)
            
            # Apply header/footer removal if requested
            if remove_headers_footers:
                cleaned_text = self._remove_headers_footers_from_text(result.markdown)
                return DocumentConverterResult(markdown=cleaned_text)
            else:
                return result
        
        # Process each page separately
        result_parts = []
        first_page = True
        
        for page_content in pages:
            # Convert page HTML to markdown
            page_result = self._html_converter.convert_string(page_content)
            page_markdown = page_result.markdown.strip()
            
            # Add page separator if this is not the first page and page has content
            if not first_page and page_markdown:
                result_parts.append("\n\n---\n\n")
            
            # Add page content
            if page_markdown:
                result_parts.append(page_markdown)
            
            first_page = False
        
        # Combine all parts
        full_text = "".join(result_parts)
        
        # Apply header/footer removal if requested
        if remove_headers_footers:
            cleaned_text = self._remove_headers_footers_from_text(full_text)
            return DocumentConverterResult(markdown=cleaned_text)
        else:
            return DocumentConverterResult(markdown=full_text)

    def _extract_pages_from_docx(self, docx_stream: BinaryIO) -> List[str]:
        """
        Extract individual pages from a DOCX file by detecting page breaks.
        Returns a list of HTML content for each page.
        """
        # Reset stream position
        docx_stream.seek(0)
        
        pages = []
        current_page_content = []
        
        try:
            with zipfile.ZipFile(docx_stream, 'r') as zip_file:
                # Read the main document XML
                if 'word/document.xml' in zip_file.namelist():
                    document_xml = zip_file.read('word/document.xml').decode('utf-8')
                    
                    # Parse the XML to find page breaks
                    import xml.etree.ElementTree as ET
                    
                    # Define namespaces
                    namespaces = {
                        'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
                    }
                    
                    # Parse the XML
                    root = ET.fromstring(document_xml)
                    
                    # Find all paragraphs
                    paragraphs = root.findall('.//w:p', namespaces)
                    
                    for paragraph in paragraphs:
                        # Check if this paragraph contains a page break
                        page_breaks = paragraph.findall('.//w:br[@w:type="page"]', namespaces)
                        
                        # Convert paragraph to HTML
                        paragraph_html = self._paragraph_to_html(paragraph, namespaces)
                        
                        if page_breaks:
                            # This paragraph contains a page break, start a new page
                            if current_page_content:
                                pages.append(''.join(current_page_content))
                                current_page_content = []
                        
                        if paragraph_html.strip():
                            current_page_content.append(paragraph_html)
                    
                    # Add the last page if it has content
                    if current_page_content:
                        pages.append(''.join(current_page_content))
        
        except Exception as e:
            # If page extraction fails, fall back to single page conversion
            print(f"Warning: Could not extract pages from DOCX: {e}")
            docx_stream.seek(0)
            # Fall back to normal conversion without page separation
            style_map = None  # Default style map
            html_content = mammoth.convert_to_html(docx_stream, style_map=style_map).value
            return [html_content]
        
        return pages

    def _paragraph_to_html(self, paragraph, namespaces):
        """
        Convert a paragraph XML element to HTML string.
        """
        # This is a simplified conversion - in practice, you might want to use
        # a more robust XML to HTML conversion library
        html_parts = ['<p>']
        
        # Extract text from the paragraph
        text_elements = paragraph.findall('.//w:t', namespaces)
        for text_elem in text_elements:
            if text_elem.text:
                html_parts.append(text_elem.text)
        
        html_parts.append('</p>')
        return ''.join(html_parts)

    def _remove_headers_footers_from_text(self, text: str) -> str:
        """
        Remove headers and footers from DOCX text using the same duplicate-line
        detection logic employed by the PDF converter.

        Steps:
        1. Split the document into pages using the standard page separator
           ``\n\n---\n\n``.
        2. Collect up to the first two and last two **non-empty** lines from
           every page.
        3. Identify lines that repeat across pages – these are treated as
           headers or footers.
        4. Remove up to two occurrences of these duplicate lines from the start
           and end of each page.
        """
        # Split pages using the same separator that _convert_with_options adds
        pages = text.split('\n\n---\n\n')

        # Fallback to the simple heuristic when we cannot detect multiple pages
        if len(pages) <= 1:
            return self._remove_headers_footers_simple(text)

        # Collect candidate header/footer lines
        last_lines: List[str] = []
        first_lines: List[str] = []

        for page in pages:
            page = page.strip()
            if not page:
                continue

            lines = page.split('\n')

            # Last two non-empty lines
            found_last: List[str] = []
            for line in reversed(lines):
                candidate = line.strip()
                if candidate:
                    found_last.append(candidate)
                    if len(found_last) >= 2:
                        break
            last_lines.extend(found_last)

            # First two non-empty lines
            found_first: List[str] = []
            for line in lines:
                candidate = line.strip()
                if candidate:
                    found_first.append(candidate)
                    if len(found_first) >= 2:
                        break
            first_lines.extend(found_first)

        # Not enough data to establish patterns – just return original text
        if len(last_lines) <= 1 and len(first_lines) <= 1:
            return text

        from collections import Counter

        all_lines = last_lines + first_lines
        line_counts = Counter(all_lines)
        duplicate_lines = {ln for ln, cnt in line_counts.items() if cnt > 1}

        # Debug output mirroring PdfConverter for easy comparison
        print(f"DEBUG: Found {len(duplicate_lines)} duplicate header/footer lines")
        for idx, dup in enumerate(duplicate_lines, 1):
            print(f"  D{idx}. '{dup}' (appears {line_counts[dup]} times)")

        lines_to_remove = duplicate_lines
        print(f"DEBUG: Total unique lines scheduled for removal (duplicates only): {len(lines_to_remove)}")

        cleaned_pages: List[str] = []
        for page in pages:
            page = page.strip()
            if not page:
                continue

            lines = page.split('\n')

            # Remove up to two duplicate lines from the start
            lines_removed_from_start = 0
            while lines and lines_removed_from_start < 2:
                candidate = lines[0].strip()
                if candidate and candidate in lines_to_remove:
                    lines.pop(0)
                    lines_removed_from_start += 1
                else:
                    break

            # Remove up to two duplicate lines from the end
            lines_removed_from_end = 0
            while lines and lines_removed_from_end < 2:
                candidate = lines[-1].strip()
                if candidate and candidate in lines_to_remove:
                    lines.pop()
                    lines_removed_from_end += 1
                else:
                    break

            cleaned_pages.append('\n'.join(lines))

        # Re-assemble the document using the same separator
        return '\n\n---\n\n'.join(cleaned_pages)

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using regex. Handles common sentence boundaries.
        """
        # This regex splits on period, exclamation, or question mark followed by whitespace or end of string
        sentence_endings = re.compile(r'(?<=[.!?])\s+')
        sentences = sentence_endings.split(text)
        return [s.strip() for s in sentences if s.strip()]

    def _find_sentence_patterns(self, sentences: List[str]) -> set:
        """
        Find sentences with similar patterns (like page numbers, copyright notices, etc.)
        """
        if len(sentences) < 2:
            return set()
        
        pattern_sentences = set()
        
        # Strategy 1: Find sentences that contain numbers and share common words
        for i, sentence in enumerate(sentences):
            # Check if sentence contains numbers
            if not re.search(r'\d', sentence):
                continue
                
            words = set(re.findall(r'\b\w+\b', sentence))
            if len(words) == 0:
                continue
                
            # Count how many other sentences share meaningful words with this sentence
            shared_count = 0
            for j, other_sentence in enumerate(sentences):
                if i != j:
                    other_words = set(re.findall(r'\b\w+\b', other_sentence))
                    shared_words = words & other_words
                    # Only count if they share meaningful words (not just common words)
                    meaningful_shared = shared_words - {'the', 'of', 'to', 'and', 'or', 'in', 'on', 'at', 'for', 'with', 'by', 'from', 'up', 'down', 'out', 'off', 'over', 'under', 'into', 'onto', 'upon', 'within', 'without', 'through', 'throughout', 'during', 'before', 'after', 'since', 'until', 'while', 'where', 'when', 'why', 'how', 'what', 'which', 'who', 'whom', 'whose', 'this', 'that', 'these', 'those', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'must', 'shall'}
                    if len(meaningful_shared) >= 2:  # Require at least 2 meaningful shared words
                        shared_count += 1
            
            # If this sentence shares meaningful words with at least 2 other sentences, it's likely a pattern
            if shared_count >= 2:
                pattern_sentences.add(sentence)
        
        # Strategy 2: Find sentences with similar structure (like "Page X of Y")
        for i, sentence in enumerate(sentences):
            # Create a structure pattern: replace numbers with 'N', keep other chars
            structure = re.sub(r'\d+', 'N', sentence)
            
            # Only consider sentences that have a meaningful structure
            if len(structure) < 5 or structure.count('N') < 2:
                continue
            
            # Count how many other sentences have the same structure
            structure_count = 0
            for j, other_sentence in enumerate(sentences):
                if i != j:
                    other_structure = re.sub(r'\d+', 'N', other_sentence)
                    if structure == other_structure:
                        structure_count += 1
            
            # If this sentence has the same structure as at least 2 other sentences, it's likely a pattern
            if structure_count >= 2:
                pattern_sentences.add(sentence)
        
        return pattern_sentences

    def _remove_headers_footers_simple(self, text: str) -> str:
        """
        Simple header/footer removal for DOCX documents without page separators.
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
