#!/usr/bin/env python3
"""
Test script for the new header/footer removal feature in MarkItDown.
"""

import sys
import os
from pathlib import Path
from typing import List

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import directly from the local source
from markitdown._markitdown import MarkItDown
from markitdown.converters._pdf_converter import PdfConverter

def test_header_footer_removal():
    """Test the header/footer removal feature."""
    
    # Initialize MarkItDown
    md = MarkItDown(enable_plugins=False)
    
    # Debug: Check which PdfConverter is being used
    print("Checking which PdfConverter is being used...")
    pdf_converter_instance = None
    for registration in md._converters:
        if isinstance(registration.converter, PdfConverter):
            pdf_converter_instance = registration.converter
            break
    
    if pdf_converter_instance:
        print(f"PdfConverter module: {PdfConverter.__module__}")
        print(f"Has debug method: {hasattr(pdf_converter_instance, '_remove_headers_footers_from_text')}")
        print(f"Has find_common_patterns method: {hasattr(pdf_converter_instance, '_find_common_patterns')}")
    else:
        print("No PdfConverter found in registered converters!")
    
    # Test file path
    test_file = "tests/test_files/sha.pdf"
    
    if not os.path.exists(test_file):
        print(f"Test file not found: {test_file}")
        print("Please ensure you have a test PDF file available.")
        return
    
    print("Testing PDF conversion with header/footer removal...")
    print("=" * 50)
    
    try:
        
        
        # Test 3: With both page separators and header/footer removal
        print("\n3. With page separators AND header/footer removal:")
        print("-" * 40)
        result3 = md.convert(test_file, 
                           add_page_separators=True, 
                           remove_headers_footers=True)
        
        # Debug: Let's also get the result without header/footer removal to compare
        print("\nGetting result without header/footer removal for comparison...")
        result_only_page_separators = md.convert(test_file, 
                                          add_page_separators=True, 
                                          remove_headers_footers=False)
        
        print(f"\nLength with header/footer removal: {len(result3.markdown)}")
        print(f"Length without header/footer removal: {len(result_only_page_separators.markdown)}")
        print(f"Difference: {len(result_only_page_separators.markdown) - len(result3.markdown)} characters")
        
        # Check if the results are identical
        if result3.markdown == result_only_page_separators.markdown:
            print("⚠️  WARNING: Results are identical! Header/footer removal may not be working.")
            
        
        # Save the output to a file
                # Output original clean text
        output_path = "output_page_separated_no_headers.md"
        clean_content = clean_text(result3.text_content)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(clean_content)
        
        # Chunk the clean text and output to separate file
        from text_chunker import TextChunker
        
        chunker = TextChunker()
        
        
        # Chunk the text (adjust token_limit and overlap_size as needed)
        chunks = chunker.chunk_text(
            text=clean_content,
            token_limit=500,  # Adjust based on your needs
            overlap_size=50   # Adjust based on your needs
        )
        
        # Output chunked text
        chunked_output_path = "output_chunked.md"
        with open(chunked_output_path, "w", encoding="utf-8") as f:
            f.write(f"# Chunked Document\n\n")
            f.write(f"Original text tokens: {chunker.token_count(clean_content)}\n")
            f.write(f"Number of chunks: {len(chunks)}\n\n")
            
            for i, chunk in enumerate(chunks, 1):
                f.write(f"## Chunk {i}\n\n")
                f.write(f"**Tokens:** {chunker.token_count(chunk)}\n\n")
                f.write(chunk)
                f.write("\n\n\n\n")
        
        print(f"Original text saved to: {output_path}")
        print(f"Chunked text saved to: {chunked_output_path}")
        print(f"Total chunks: {len(chunks)}")
        print(f"Total tokens: {chunker.token_count(clean_content)}")
        print(f"\nSaved Markdown with page separators and no headers/footers to: {output_path}")
        with open("original.md", "w", encoding="utf-8") as f:
            f.write(clean_text(result_only_page_separators.text_content))
        print(f"\nSaved Markdown with page separators and no headers/footers to: original.md")
    
    except Exception as e:
        print(f"Error during conversion: {e}")
        print("\nThis might be because PyMuPDF is not installed.")
        print("Install it with: pip install PyMuPDF")
import re

_whitespace_re = re.compile(r"\s+")

def clean_text(text: str) -> str:
    """Clean and normalize text"""
    if not text:
        return ""

    # Remove triple dashes and normalize whitespace
    text = text.replace('---', ' ').replace('\n', ' ').replace('\r', ' ')
    text = _whitespace_re.sub(" ", text)
    return text.strip()



def test_header_footer_removal_with_sample_text():
    """Test the header/footer removal logic with sample text."""
    
    # Create a PDF converter instance directly
    pdf_converter = PdfConverter()
    
    # Sample text with headers and footers
    sample_text = """
    
ELI:  http://data.europa.eu/eli/reg_del/2023/2772/oj

---

16/284

---

ELI:  http://data.europa.eu/eli/reg_del/2023/2772/oj

---

18/284

---

i love summer
"""
    
    print("\nTesting header/footer removal logic with sample text:")
    print(pdf_converter._remove_headers_footers_from_text(sample_text))
    

if __name__ == "__main__":
    
    # Test with sample text first
    # test_header_footer_removal_with_sample_text()
    
    # Test with actual PDF file
    test_header_footer_removal()
   