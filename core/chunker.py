"""
Text chunker for Limbus Guide Plugin
Splits documents into chunks with overlap for better retrieval
"""
from typing import List, Dict
import re


class Chunker:
    """Text chunker with Chinese character counting and overlap support"""
    
    def __init__(self, chunk_size: int = 800, overlap: int = 120):
        """
        Initialize chunker
        
        Args:
            chunk_size: Maximum chunk size in Chinese characters
            overlap: Overlap between chunks in characters
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def count_chars(self, text: str) -> int:
        """
        Count characters (Chinese characters count as 1, ASCII as 0.5)
        This provides a rough approximation of visual length
        """
        count = 0
        for char in text:
            if ord(char) > 127:  # Non-ASCII (Chinese, etc.)
                count += 1
            else:
                count += 0.5
        return int(count)
    
    def split_into_chunks(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks
        
        Attempts to split at natural boundaries (paragraphs, sentences)
        """
        if not text or not text.strip():
            return []
        
        # Normalize text
        text = text.strip()
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # First, try to split by major sections (headers)
        sections = self._split_by_headers(text)
        
        chunks = []
        for section in sections:
            section_chunks = self._split_section(section)
            chunks.extend(section_chunks)
        
        # Apply overlap
        if self.overlap > 0 and len(chunks) > 1:
            chunks = self._apply_overlap(chunks)
        
        return chunks
    
    def _split_by_headers(self, text: str) -> List[str]:
        """Split text by major headers"""
        # Match headers like 【xxx】, # xxx, ## xxx
        header_pattern = r'(?=(?:^|\n)(?:【|#{1,3}\s))'
        
        parts = re.split(header_pattern, text)
        parts = [p.strip() for p in parts if p.strip()]
        
        return parts if parts else [text]
    
    def _split_section(self, text: str) -> List[str]:
        """Split a section into appropriately sized chunks"""
        char_count = self.count_chars(text)
        
        if char_count <= self.chunk_size:
            return [text]
        
        chunks = []
        paragraphs = text.split('\n\n')
        
        current_chunk = ""
        current_size = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_size = self.count_chars(para)
            
            # If single paragraph is too large, split by sentences
            if para_size > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                    current_size = 0
                
                # Split large paragraph by sentences
                sentence_chunks = self._split_by_sentences(para)
                chunks.extend(sentence_chunks)
                continue
            
            # Check if adding this paragraph exceeds limit
            if current_size + para_size > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para
                current_size = para_size
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
                current_size += para_size
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _split_by_sentences(self, text: str) -> List[str]:
        """Split text by sentences when paragraph is too large"""
        # Chinese and English sentence endings
        sentence_pattern = r'([。！？!?；;])'
        
        parts = re.split(sentence_pattern, text)
        
        # Recombine sentence with its ending punctuation
        sentences = []
        i = 0
        while i < len(parts):
            sentence = parts[i]
            if i + 1 < len(parts) and re.match(sentence_pattern, parts[i + 1]):
                sentence += parts[i + 1]
                i += 2
            else:
                i += 1
            if sentence.strip():
                sentences.append(sentence.strip())
        
        # Group sentences into chunks
        chunks = []
        current_chunk = ""
        current_size = 0
        
        for sentence in sentences:
            sentence_size = self.count_chars(sentence)
            
            if current_size + sentence_size > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
                current_size = sentence_size
            else:
                if current_chunk:
                    current_chunk += sentence
                else:
                    current_chunk = sentence
                current_size += sentence_size
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _apply_overlap(self, chunks: List[str]) -> List[str]:
        """Apply overlap between consecutive chunks"""
        if len(chunks) <= 1:
            return chunks
        
        result = [chunks[0]]
        
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            curr_chunk = chunks[i]
            
            # Get overlap from end of previous chunk
            overlap_text = self._get_tail_text(prev_chunk, self.overlap)
            
            # Prepend overlap to current chunk if it doesn't already start with it
            if overlap_text and not curr_chunk.startswith(overlap_text[:20]):
                curr_chunk = f"...{overlap_text}\n\n{curr_chunk}"
            
            result.append(curr_chunk)
        
        return result
    
    def _get_tail_text(self, text: str, char_count: int) -> str:
        """Get the last n characters of text, breaking at word/sentence boundary"""
        if self.count_chars(text) <= char_count:
            return text
        
        # Find approximate position
        pos = len(text)
        count = 0
        
        while pos > 0 and count < char_count:
            pos -= 1
            char = text[pos]
            if ord(char) > 127:
                count += 1
            else:
                count += 0.5
        
        # Try to break at a natural boundary
        tail = text[pos:]
        
        # Find sentence start
        for pattern in ['\n\n', '\n', '。', '！', '？', '；', '. ', '! ', '? ']:
            idx = tail.find(pattern)
            if idx != -1 and idx < len(tail) // 2:
                tail = tail[idx + len(pattern):]
                break
        
        return tail.strip()
    
    def process_document(self, text: str, doc_name: str = "") -> List[Dict]:
        """
        Process a document and return chunks with metadata
        
        Returns list of dicts with 'content', 'index', 'doc_name' keys
        """
        chunks = self.split_into_chunks(text)
        
        return [
            {
                'content': chunk,
                'index': i,
                'doc_name': doc_name,
                'char_count': self.count_chars(chunk)
            }
            for i, chunk in enumerate(chunks)
        ]
