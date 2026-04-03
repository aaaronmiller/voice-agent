"""
Sentence Chunker for Streaming TTS

Splits LLM token stream at sentence boundaries for parallel
synthesis and playback.
"""

import re
from typing import AsyncIterator


# Sentence ending punctuation followed by whitespace
SENTENCE_END = re.compile(r'(?<=[.!?])\s+')


async def chunk_sentences(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """
    Buffer LLM tokens and yield complete sentences.
    
    Yields each sentence as soon as a sentence-ending boundary is detected,
    enabling parallel TTS synthesis and playback.
    
    Args:
        token_stream: Async iterator of LLM tokens
    
    Yields:
        Complete sentences (stripped)
    """
    buffer = ""
    
    async for token in token_stream:
        buffer += token
        
        # Split on sentence boundaries
        parts = SENTENCE_END.split(buffer)
        
        # Yield all complete sentences, keep the last (possibly incomplete) part
        while len(parts) > 1:
            sentence = parts.pop(0).strip()
            if sentence:
                yield sentence
        
        buffer = " ".join(parts) if parts else ""
    
    # Yield any remaining text (final sentence without ending punctuation)
    if buffer.strip():
        yield buffer.strip()


async def chunk_words(token_stream: AsyncIterator[str], word_count: int = 3) -> AsyncIterator[str]:
    """
    Buffer LLM tokens and yield after every N words.
    
    Alternative to sentence chunking for faster first audio.
    Less natural but lower latency.
    
    Args:
        token_stream: Async iterator of LLM tokens
        word_count: Number of words per chunk
    
    Yields:
        Word groups (stripped)
    """
    buffer = ""
    words = []
    
    async for token in token_stream:
        buffer += token
        
        # Count words
        current_words = buffer.split()
        
        if len(current_words) >= word_count:
            # Yield complete chunk
            yield " ".join(current_words[:word_count])
            buffer = " ".join(current_words[word_count:])
    
    # Yield remaining
    if buffer.strip():
        yield buffer.strip()
