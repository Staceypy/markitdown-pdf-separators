import re
import sys
import io

from typing import BinaryIO, Any, List


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
        full_text_raw = self.clean_text(full_text)
        # Remove headers and footers if requested (after combining all pages)
        if remove_headers_footers and full_text_raw:
            removed_headers_footers_full_text = self._remove_headers_footers_from_text(full_text_raw)
        else:
            removed_headers_footers_full_text = full_text_raw
        
        return DocumentConverterResult(markdown=removed_headers_footers_full_text)

    def clean_text(self,text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        _whitespace_re = re.compile(r"\s+")


        # Remove triple dashes and normalize whitespace
        # text = text.replace('---', ' ').replace('\n', ' ').replace('\r', ' ')
        text = text.replace('\n', ' ').replace('\r', ' ')
        text = _whitespace_re.sub(" ", text)
        return text.strip()

    def _remove_headers_footers_from_text(self, text: str) -> str:
        """
        Remove headers and footers from text using intelligent pattern detection:
        1. Split text into sentences and identify page boundaries
        2. Find duplicate sentences across pages (headers/footers)
        3. Remove identified header/footer sentences
        """
        
        # Split by page separators to get individual pages
        pages = text.split('---')
        
        if len(pages) <= 1:  # No page separators, use simple approach
            return self._remove_headers_footers_simple(text)
        
        print(f"DEBUG: Processing {len(pages)} pages total")
        
        # Split each page into sentences
        all_sentences = []
        page_sentences = []
        
        for page in pages:
            page = page.strip()
            if page:
                # Split page into sentences
                sentences = self._split_into_sentences(page)
                page_sentences.append(sentences)
                all_sentences.extend(sentences)
        
        print(f"DEBUG: Total sentences across all pages: {len(all_sentences)}")
        
        # Find duplicate sentences (likely headers/footers)
        from collections import Counter
        sentence_counts = Counter(all_sentences)
        duplicate_sentences = {sentence for sentence, count in sentence_counts.items() if count > 1}
        
        print(f"DEBUG: Found {len(duplicate_sentences)} duplicate sentences across all pages")
        if duplicate_sentences:
            print("DEBUG: Duplicate sentences content:")
            for i, sentence in enumerate(list(duplicate_sentences)[:5]):  # Show first 5
                print(f"  {i+1}. '{sentence[:100]}...' (appears {sentence_counts[sentence]} times)")
            if len(duplicate_sentences) > 5:
                print(f"  ... and {len(duplicate_sentences) - 5} more duplicate sentences")
        
        # Find pattern-based sentences (similar structure but different content)
        pattern_sentences = self._find_sentence_patterns(all_sentences)
        
        print(f"DEBUG: Found {len(pattern_sentences)} pattern-based sentences to remove")
        if pattern_sentences:
            print("DEBUG: Pattern sentences content:")
            for i, sentence in enumerate(list(pattern_sentences)[:5]):  # Show first 5
                print(f"  {i+1}. '{sentence[:100]}...' (appears {sentence_counts.get(sentence, 1)} times)")
            if len(pattern_sentences) > 5:
                print(f"  ... and {len(pattern_sentences) - 5} more pattern sentences")
        
        # Combine all sentences to remove
        sentences_to_remove = duplicate_sentences | pattern_sentences
        
        # Calculate total sentences being removed
        total_removals = sum(sentence_counts[sentence] for sentence in sentences_to_remove)
        print(f"DEBUG: Total sentences to remove: {len(sentences_to_remove)} unique sentences ({total_removals} total occurrences)")
        
        # Remove these sentences from all pages
        cleaned_pages = []
        for sentences in page_sentences:
            # Remove sentences that are in our removal list
            cleaned_sentences = [s for s in sentences if s not in sentences_to_remove]
            cleaned_page = ' '.join(cleaned_sentences)
            if cleaned_page.strip():
                cleaned_pages.append(cleaned_page)
        
        # Rejoin with page separators
        result = ' --- '.join(cleaned_pages)
        print(f"DEBUG: Header/footer removal complete. Output length: {len(result)} characters")
        return result

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
                    shared_words = words & other_words  # Intersection
                    # Only count if they share meaningful words (not just common words like "the", "of", "to")
                    meaningful_shared = shared_words - {'the', 'of', 'to', 'and', 'or', 'in', 'on', 'at', 'for', 'with', 'by', 'from', 'up', 'down', 'out', 'off', 'over', 'under', 'into', 'onto', 'upon', 'within', 'without', 'through', 'throughout', 'during', 'before', 'after', 'since', 'until', 'while', 'where', 'when', 'why', 'how', 'what', 'which', 'who', 'whom', 'whose', 'this', 'that', 'these', 'those', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'must', 'shall'}
                    if len(meaningful_shared) >= 2:  # Require at least 2 meaningful shared words
                        shared_count += 1
            
            # If this line shares meaningful words with at least 2 other lines, it's likely a pattern
            if shared_count >= 2:
                pattern_lines.add(lines[i])
        
        # Strategy 2: Find lines with similar structure (like "16/284", "18/284")
        for i, line in enumerate(lines):
            # Create a structure pattern: replace numbers with 'N', keep other chars
            structure = re.sub(r'\d+', 'N', line)
            
            # Only consider lines that have a meaningful structure (not just single numbers)
            if len(structure) < 3 or structure.count('N') < 2:
                continue
            
            # Count how many other lines have the same structure
            structure_count = 0
            for j, other_line in enumerate(lines):
                if i != j:
                    other_structure = re.sub(r'\d+', 'N', other_line)
                    if structure == other_structure:
                        structure_count += 1
            
            # If this line has the same structure as at least 2 other lines, it's likely a pattern
            if structure_count >= 2:
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
