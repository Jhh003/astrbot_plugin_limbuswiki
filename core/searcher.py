"""
Search/Retrieval module for Limbus Guide Plugin
Implements BM25-based search with tag weighting
"""
import re
import math
from typing import List, Dict, Tuple, Optional, Set
from collections import Counter


class Searcher:
    """BM25-based searcher with tag weighting for Limbus Company content"""
    
    # BM25 parameters
    K1 = 1.5
    B = 0.75
    
    # Tag boost factor
    TAG_BOOST = 1.5
    
    # Group scope boost factor
    GROUP_BOOST = 1.2
    
    # Pattern to remove non-Chinese characters for Chinese text extraction
    NON_CHINESE_PATTERN = re.compile(r'[a-zA-Z0-9\s\[\]【】《》（）().,，。！!？?；;：:""\'\']+')
    # Pattern to extract English words and numbers
    ENGLISH_PATTERN = re.compile(r'[a-zA-Z0-9]+')
    
    def __init__(self, chunks: List[Dict] = None, alias_map: Dict[str, str] = None):
        """
        Initialize searcher
        
        Args:
            chunks: List of chunk dicts with 'content', 'tags', 'scope' keys
            alias_map: Mapping of aliases to canonical terms
        """
        self.chunks = chunks or []
        self.alias_map = alias_map or {}
        
        # BM25 index structures
        self.doc_freq: Dict[str, int] = {}  # Document frequency for each term
        self.doc_lens: List[int] = []  # Length of each document
        self.avg_doc_len: float = 0
        self.term_freqs: List[Dict[str, int]] = []  # Term frequencies per document
        
        if self.chunks:
            self._build_index()
    
    def update_chunks(self, chunks: List[Dict]):
        """Update chunks and rebuild index"""
        self.chunks = chunks
        self._build_index()
    
    def update_aliases(self, alias_map: Dict[str, str]):
        """Update alias mapping"""
        self.alias_map = alias_map
    
    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize text for indexing/searching
        Uses simple Chinese character + bigram + English word tokenization
        """
        tokens = []
        text = text.lower()
        
        # Extract English words and numbers using class pattern
        english_tokens = self.ENGLISH_PATTERN.findall(text)
        tokens.extend(english_tokens)
        
        # Extract Chinese characters using class pattern
        chinese_text = self.NON_CHINESE_PATTERN.sub(' ', text)
        chinese_chars = [c for c in chinese_text if c.strip()]
        
        # Add unigrams
        tokens.extend(chinese_chars)
        
        # Add bigrams for Chinese
        for i in range(len(chinese_chars) - 1):
            bigram = chinese_chars[i] + chinese_chars[i + 1]
            tokens.append(bigram)
        
        return tokens
    
    def _build_index(self):
        """Build BM25 index from chunks"""
        self.doc_freq = {}
        self.doc_lens = []
        self.term_freqs = []
        
        for chunk in self.chunks:
            content = chunk.get('content', '')
            tokens = self._tokenize(content)
            
            # Count term frequencies
            tf = Counter(tokens)
            self.term_freqs.append(dict(tf))
            
            # Update document frequencies
            for term in set(tokens):
                self.doc_freq[term] = self.doc_freq.get(term, 0) + 1
            
            # Store document length
            self.doc_lens.append(len(tokens))
        
        # Calculate average document length
        if self.doc_lens:
            self.avg_doc_len = sum(self.doc_lens) / len(self.doc_lens)
        else:
            self.avg_doc_len = 0
    
    def _apply_aliases(self, query: str) -> str:
        """Apply alias substitutions to query"""
        result = query.lower()
        
        for alias, canonical in self.alias_map.items():
            # Case-insensitive replacement
            pattern = re.compile(re.escape(alias), re.IGNORECASE)
            result = pattern.sub(canonical, result)
        
        return result
    
    def _extract_query_tags(self, query: str) -> Set[str]:
        """Extract potential tag matches from query"""
        tags = set()
        query_lower = query.lower()
        
        # Check for status keywords
        status_keywords = {
            'burn': ['burn', '燃烧', '烧伤'],
            'bleed': ['bleed', '流血', '出血'],
            'tremor': ['tremor', '震颤'],
            'rupture': ['rupture', '破裂'],
            'sinking': ['sinking', '沉沦'],
            'poise': ['poise', '蓄力', '架势'],
        }
        
        for status, keywords in status_keywords.items():
            for kw in keywords:
                if kw in query_lower:
                    tags.add(f'状态:{status.capitalize()}')
                    break
        
        # Check for mode keywords
        mode_keywords = {
            '主线': ['主线', '章节'],
            '镜牢': ['镜牢', 'md', '镜像'],
            '铁道': ['铁道', 'rr'],
            '活动': ['活动'],
        }
        
        for mode, keywords in mode_keywords.items():
            for kw in keywords:
                if kw in query_lower:
                    tags.add(mode)
                    break
        
        # Check for mechanics keywords
        if any(kw in query_lower for kw in ['拼点', 'clash', '硬币', '速度']):
            tags.add('拼点/冲突')
        
        if any(kw in query_lower for kw in ['ego', '侵蚀']):
            tags.add('EGO')
            tags.add('EGO机制')
        
        if any(kw in query_lower for kw in ['配队', '阵容', '队伍']):
            tags.add('配队/阵容')
        
        if any(kw in query_lower for kw in ['人格', 'identity', 'id']):
            tags.add('人格')
        
        return tags
    
    def _calculate_bm25_score(self, query_tokens: List[str], doc_idx: int) -> float:
        """Calculate BM25 score for a document"""
        score = 0.0
        doc_len = self.doc_lens[doc_idx]
        tf_dict = self.term_freqs[doc_idx]
        num_docs = len(self.chunks)
        
        for term in query_tokens:
            if term not in self.doc_freq:
                continue
            
            # IDF
            df = self.doc_freq[term]
            idf = math.log((num_docs - df + 0.5) / (df + 0.5) + 1)
            
            # TF with length normalization
            tf = tf_dict.get(term, 0)
            tf_norm = (tf * (self.K1 + 1)) / (
                tf + self.K1 * (1 - self.B + self.B * doc_len / self.avg_doc_len)
            )
            
            score += idf * tf_norm
        
        return score
    
    def search(self, query: str, top_k: int = 6, 
               group_id: Optional[str] = None) -> List[Dict]:
        """
        Search for relevant chunks
        
        Args:
            query: Search query
            top_k: Number of results to return
            group_id: Optional group ID for boosting group-specific results
            
        Returns:
            List of chunk dicts with 'score' and 'score_breakdown' added
        """
        if not self.chunks:
            return []
        
        # Apply alias substitutions
        processed_query = self._apply_aliases(query)
        
        # Tokenize query
        query_tokens = self._tokenize(processed_query)
        
        if not query_tokens:
            return []
        
        # Extract tags from query
        query_tags = self._extract_query_tags(processed_query)
        
        # Score all chunks
        scored_chunks = []
        
        for idx, chunk in enumerate(self.chunks):
            # Base BM25 score
            bm25_score = self._calculate_bm25_score(query_tokens, idx)
            
            # Tag boost
            tag_score = 0.0
            chunk_tags = set(chunk.get('tags', []))
            matching_tags = query_tags & chunk_tags
            if matching_tags:
                tag_score = len(matching_tags) * self.TAG_BOOST
            
            # Group boost
            group_score = 0.0
            if group_id and chunk.get('scope') == 'group' and chunk.get('group_id') == group_id:
                group_score = self.GROUP_BOOST
            
            total_score = bm25_score + tag_score + group_score
            
            if total_score > 0:
                result = dict(chunk)
                result['score'] = total_score
                result['score_breakdown'] = {
                    'bm25': bm25_score,
                    'tag_boost': tag_score,
                    'group_boost': group_score,
                    'matching_tags': list(matching_tags)
                }
                scored_chunks.append(result)
        
        # Sort by score and return top_k
        scored_chunks.sort(key=lambda x: x['score'], reverse=True)
        
        return scored_chunks[:top_k]
    
    def search_with_debug(self, query: str, top_k: int = 6,
                         group_id: Optional[str] = None) -> Dict:
        """
        Search with detailed debug information
        
        Returns:
            Dict with 'results', 'query_info', 'stats' keys
        """
        processed_query = self._apply_aliases(query)
        query_tokens = self._tokenize(processed_query)
        query_tags = self._extract_query_tags(processed_query)
        
        results = self.search(query, top_k, group_id)
        
        return {
            'results': results,
            'query_info': {
                'original_query': query,
                'processed_query': processed_query,
                'tokens': query_tokens,
                'extracted_tags': list(query_tags),
                'alias_substitutions': [
                    f"{k} -> {v}" for k, v in self.alias_map.items()
                    if k.lower() in query.lower()
                ]
            },
            'stats': {
                'total_chunks': len(self.chunks),
                'results_count': len(results),
                'avg_doc_len': self.avg_doc_len,
                'unique_terms': len(self.doc_freq)
            }
        }


class SimpleSearcher:
    """
    Fallback simple searcher using basic keyword matching
    Used when no dependencies are available
    """
    
    def __init__(self, chunks: List[Dict] = None, alias_map: Dict[str, str] = None):
        self.chunks = chunks or []
        self.alias_map = alias_map or {}
    
    def update_chunks(self, chunks: List[Dict]):
        self.chunks = chunks
    
    def update_aliases(self, alias_map: Dict[str, str]):
        self.alias_map = alias_map
    
    def search(self, query: str, top_k: int = 6,
               group_id: Optional[str] = None) -> List[Dict]:
        """Simple keyword-based search"""
        if not self.chunks:
            return []
        
        # Apply aliases
        processed_query = query.lower()
        for alias, canonical in self.alias_map.items():
            processed_query = processed_query.replace(alias.lower(), canonical.lower())
        
        # Extract keywords (simple splitting)
        keywords = set(processed_query.split())
        
        # Score chunks
        scored = []
        for chunk in self.chunks:
            content_lower = chunk.get('content', '').lower()
            
            # Count keyword matches
            match_count = sum(1 for kw in keywords if kw in content_lower)
            
            if match_count > 0:
                # Bonus for group match
                if group_id and chunk.get('scope') == 'group' and chunk.get('group_id') == group_id:
                    match_count *= 1.2
                
                result = dict(chunk)
                result['score'] = match_count
                scored.append(result)
        
        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:top_k]
