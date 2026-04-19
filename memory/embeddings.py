"""Embedding utilities for memory operations."""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Optional

logger = logging.getLogger("aetheros.memory.embeddings")


class SimpleEmbedder:
    """Lightweight text embedder using character n-gram hashing.
    
    Used as fallback when external embedding models aren't available.
    This is a bag-of-character-ngrams approach with locality-sensitive hashing.
    """

    def __init__(self, dimensions: int = 128, ngram_range: tuple[int, int] = (2, 4)):
        self.dimensions = dimensions
        self.ngram_min, self.ngram_max = ngram_range

    def embed(self, text: str) -> list[float]:
        """Generate a fixed-dimension embedding vector."""
        text = text.lower().strip()
        if not text:
            return [0.0] * self.dimensions

        vector = [0.0] * self.dimensions

        # Extract character n-grams
        for n in range(self.ngram_min, self.ngram_max + 1):
            for i in range(len(text) - n + 1):
                ngram = text[i:i + n]
                h = int(hashlib.md5(ngram.encode()).hexdigest(), 16)
                idx = h % self.dimensions
                sign = 1 if (h // self.dimensions) % 2 == 0 else -1
                vector[idx] += sign * (1.0 / n)

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    def similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        """Cosine similarity between two vectors."""
        if len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


class TextChunker:
    """Split text into chunks for embedding."""

    def __init__(self, chunk_size: int = 500, overlap: int = 50, separator: str = "\n"):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.separator = separator

    def chunk(self, text: str) -> list[str]:
        """Split text into overlapping chunks."""
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        paragraphs = text.split(self.separator)
        current = ""

        for para in paragraphs:
            if len(current) + len(para) + 1 <= self.chunk_size:
                current = current + self.separator + para if current else para
            else:
                if current:
                    chunks.append(current.strip())
                if len(para) > self.chunk_size:
                    # Split long paragraphs by words
                    words = para.split()
                    current = ""
                    for word in words:
                        if len(current) + len(word) + 1 <= self.chunk_size:
                            current = current + " " + word if current else word
                        else:
                            chunks.append(current.strip())
                            # Add overlap from end of previous chunk
                            overlap_words = current.split()[-self.overlap // 5:] if self.overlap else []
                            current = " ".join(overlap_words) + " " + word
                else:
                    current = para

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def chunk_with_metadata(self, text: str, source: str = "") -> list[dict]:
        """Chunk text and return with positional metadata."""
        chunks = self.chunk(text)
        return [
            {
                "text": chunk,
                "index": i,
                "total_chunks": len(chunks),
                "source": source,
                "char_start": text.find(chunk[:50]),
            }
            for i, chunk in enumerate(chunks)
        ]
