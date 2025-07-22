import tiktoken
import re
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
        Split text into chunks with token limits, ensuring no duplicate sentences between adjacent chunks.
        Each chunk ends at a sentence boundary, and the next chunk starts at the next sentence.
        """
        if not text:
            return []

        # Split text into sentences
        sentences = self._split_into_sentences(text)
        chunks = []
        current_chunk = ""
        current_tokens = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            sentence_tokens = self.token_count(sentence)
            # If adding this sentence would exceed the token limit, start a new chunk
            if current_tokens + sentence_tokens > token_limit:
                if current_chunk:
                    chunks.append(self._clean_text(current_chunk))
                current_chunk = sentence
                current_tokens = sentence_tokens
            else:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
                current_tokens += sentence_tokens
        # Add the last chunk
        if current_chunk:
            chunks.append(self._clean_text(current_chunk))
        return chunks

    def token_count(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.encoding.encode(text))

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using regex. Handles common sentence boundaries.
        """
        # This regex splits on period, exclamation, or question mark followed by whitespace or end of string
        sentence_endings = re.compile(r'(?<=[.!?])\s+')
        sentences = sentence_endings.split(text)
        return [s.strip() for s in sentences if s.strip()]

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