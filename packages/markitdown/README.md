# MarkItDown with PDF Page Separators

> [!IMPORTANT]
> **MarkItDown with PDF Page Separators** is a Python package and command-line utility for converting various files to Markdown, with the addition of PDF page separator and header/footer removal functionality.
>
> This is a fork of the original [MarkItDown](https://github.com/microsoft/markitdown) project by Microsoft, adding PDF page separator and header/footer removal support.

## 🆕 New Features

### PDF Page Separators
Convert PDFs to Markdown with clear page boundaries using the `add_page_separators` parameter:

```python
from markitdown import MarkItDown

md = MarkItDown(enable_plugins=False)

# With page separators (new feature!)
result = md.convert("document.pdf", add_page_separators=True)
# Output includes "---" between pages

# Without page separators (default behavior)
result = md.convert("document.pdf", add_page_separators=False)
# Output is continuous text
```

### PDF Header/Footer Removal
Remove headers and footers from PDFs using the `remove_headers_footers` parameter:

```python
from markitdown import MarkItDown

md = MarkItDown(enable_plugins=False)

# Remove headers and footers (automatically enables page separators)
result = md.convert("document.pdf", remove_headers_footers=True)
# Output excludes common headers/footers like page numbers, copyright notices, etc.

# Combine both features explicitly
result = md.convert("document.pdf", 
                   add_page_separators=True, 
                   remove_headers_footers=True)
# Clean output with page separators and no headers/footers
```

## Installation

From PyPI:

```bash
pip install markitdown-pdf-separators[all]
```

For header/footer removal functionality:

```bash
pip install markitdown-pdf-separators[pdf-clean]
```

From source:

```bash
git clone https://github.com/yourusername/markitdown-pdf-separators.git
cd markitdown-pdf-separators
pip install -e .
```

## Usage

### Command-Line

```bash
# Basic conversion
markitdown path-to-file.pdf > document.md

# With page separators (if supported by your version)
markitdown path-to-file.pdf --add-page-separators > document.md
```

### Python API

```python
from markitdown import MarkItDown

# Initialize
md = MarkItDown(enable_plugins=False)

# Convert various file types
result = md.convert("test.xlsx")
print(result.markdown)

# Convert PDF with page separators
result = md.convert("document.pdf", add_page_separators=True)
print(result.markdown)

# Convert PDF with header/footer removal
result = md.convert("document.pdf", remove_headers_footers=True)
print(result.markdown)

# Convert PDF with both features
result = md.convert("document.pdf", 
                   add_page_separators=True, 
                   remove_headers_footers=True)
print(result.markdown)
```

## Supported File Types

- **PDF** (with page separators and header/footer removal) ✨
- Word documents (.docx)
- Excel spreadsheets (.xlsx, .xls)
- PowerPoint presentations (.pptx)
- HTML files
- Plain text files
- Images (with OCR)
- Audio files (with transcription)
- And many more...

## PDF Features

### Page Separators (`add_page_separators`)
- **Parameter**: `add_page_separators=True/False` (default: `False`)
- Extracts text page by page from PDFs
- Adds `---` (Markdown horizontal rule) between pages
- Maintains document structure and readability
- Works with multi-page documents
- Useful for maintaining page boundaries in the output

### Header/Footer Removal (`remove_headers_footers`)
- **Parameter**: `remove_headers_footers=True/False` (default: `False`)
- **Note**: Automatically enables page separators when this feature is used
- Removes common headers and footers automatically
- Detects and removes up to 2 lines from the beginning and end of each page
- Identifies duplicate content across pages (headers/footers that repeat)
- Removes page numbers, copyright notices, ELI links, and other boilerplate text
- Works with most standard document formats
- Preserves main content while cleaning up formatting
- Requires PyMuPDF dependency (`pip install markitdown-pdf-separators[pdf-clean]`)

### Using Both Features Together
You can combine both features for clean, well-structured output:

```python
result = md.convert("document.pdf", 
                   add_page_separators=True, 
                   remove_headers_footers=True)
```

This will:
1. Add page separators (`---`) between each page
2. Remove headers and footers from each page
3. Produce clean, readable Markdown output

### Performance
- Optimized for efficiency with large PDFs
- Minimal overhead compared to standard conversion
- Memory-efficient processing

### Example Output
```markdown
Page 1 content here (without headers/footers)...

---

Page 2 content here (without headers/footers)...

---

Page 3 content here (without headers/footers)...
```

## Development

This project is based on the original [MarkItDown](https://github.com/microsoft/markitdown) by Microsoft, with added PDF page separator and header/footer removal functionality.

### Key Changes:
- Added PDF page separator support
- Added PDF header/footer removal support
- Optimized performance for large documents
- Backward-compatible API

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- Original MarkItDown project by Microsoft
- Based on work by Adam Fourney and contributors

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.