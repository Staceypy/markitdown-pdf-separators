import tiktoken
from typing import List


class TextChunker:
    """
    A simple text chunker that splits text into token-limited chunks with overlap.
    """
    
    def __init__(self):
        """Initialize the chunker with tiktoken encoding."""
        self.encoding = tiktoken.get_encoding("cl100k_base")
    
    def chunk_text(
        self, text: str, token_limit: int = 500, overlap_size: int = 50
    ) -> List[str]:
        """
        Split text into chunks with token limits

        Args:
            text: Text to chunk
            token_limit: Maximum tokens per chunk
            overlap_size: Overlap between chunks in characters

        Returns:
            List of text chunks
        """
        if not text:
            return []

        # Count tokens
        num_tokens = self.token_count(text)

        if num_tokens <= token_limit:
            return [text]

        # Calculate number of chunks needed
        num_chunks = num_tokens // token_limit + (num_tokens % token_limit > 0)
        chunk_size = len(text) // num_chunks

        chunks = []
        previous_end = 0

        for i in range(num_chunks):
            if i == 0:
                start = 0
            else:
                start = (i * chunk_size) - overlap_size
                start = self._find_nearest_punctuation(text, start, "backward")

            if overlap_size == 0 and start < previous_end:
                start = previous_end

            if i < num_chunks - 1:
                end = (i + 1) * chunk_size - overlap_size
                end = self._find_nearest_punctuation(text, end, "forward")
            else:
                end = None

            chunk_text = text[start:end]
            previous_end = end

            if chunk_text.strip():
                chunks.append(self._clean_text(chunk_text))

        return chunks

    def token_count(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.encoding.encode(text))

    def _find_nearest_punctuation(
        self, content: str, index: int, direction: str = "backward"
    ) -> int:
        """Find nearest punctuation mark to split text cleanly"""
        punctuations = ".!?;"

        def is_within_number_or_abbreviation(content: str, index: int) -> bool:
            # Check if period is within a number (e.g., 3.14)
            if (
                index > 0
                and index < len(content) - 1
                and content[index] == "."
                and content[index - 1].isdigit()
                and content[index + 1].isdigit()
            ):
                return True

            # Check for nearby periods (abbreviations)
            nearby_periods = 0
            for offset in range(-5, 6):
                if offset == 0:
                    continue
                check_index = index + offset
                if 0 <= check_index < len(content) and content[check_index] == ".":
                    nearby_periods += 1
                    if nearby_periods >= 1:
                        return True
            return False

        if direction == "backward":
            while index > 0:
                if content[
                    index - 1
                ] in punctuations and not is_within_number_or_abbreviation(
                    content, index - 1
                ):
                    break
                index -= 1
        else:
            while index < len(content):
                if content[
                    index
                ] in punctuations and not is_within_number_or_abbreviation(
                    content, index
                ):
                    index += 1
                    break
                index += 1

        return index

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text chunk"""
        return text.strip()


# Usage example
if __name__ == "__main__":
    # Create chunker instance
    chunker = TextChunker()
    
    # Example text
    sample_text = """
    This is a sample text that will be chunked into smaller pieces. 
    The chunker will split the text at natural punctuation boundaries 
    while respecting token limits. It's useful for processing large 
    documents that need to be broken down into manageable pieces for 
    analysis or processing by language models.
    
    The chunker also handles overlap between chunks to maintain context 
    and ensure that important information isn't lost at chunk boundaries. 
    This is particularly important when working with documents that have 
    complex structure or when you need to maintain semantic coherence 
    across chunk boundaries.
    """
    
    # Chunk the text
    chunks = chunker.chunk_text(sample_text, token_limit=100, overlap_size=20)
    
    print(f"Original text tokens: {chunker.token_count(sample_text)}")
    print(f"Number of chunks: {len(chunks)}")
    
    for i, chunk in enumerate(chunks):
        print(f"\n--- Chunk {i+1} ---")
        print(f"Tokens: {chunker.token_count(chunk)}")
        print(chunk) 