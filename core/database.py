"""
Database module for Limbus Guide Plugin
Handles SQLite storage for documents, chunks, aliases, and group settings
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor


class Database:
    """SQLite database handler with async support via thread pool"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._executor = ThreadPoolExecutor(max_workers=2)  # Allow concurrent reads
        self._conn: Optional[sqlite3.Connection] = None
    
    async def init(self):
        """Initialize database and create tables"""
        await self._run_in_executor(self._init_db)
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get or create database connection"""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn
    
    async def _run_in_executor(self, func, *args):
        """Run blocking database operations in thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args)
    
    def _init_db(self):
        """Create database tables"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Documents table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL DEFAULT 'global',
                group_id TEXT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                raw_text_len INTEGER NOT NULL
            )
        ''')
        
        # Chunks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL,
                scope TEXT NOT NULL DEFAULT 'global',
                group_id TEXT,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                tags_json TEXT NOT NULL DEFAULT '[]',
                entities_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        ''')
        
        # Aliases table (global)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aliases (
                alias TEXT PRIMARY KEY,
                canonical TEXT NOT NULL,
                type TEXT DEFAULT 'other',
                created_at TEXT NOT NULL
            )
        ''')
        
        # Group settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_settings (
                group_id TEXT PRIMARY KEY,
                default_mode TEXT DEFAULT 'simple',
                last_import_at TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Custom templates table (for document templates)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custom_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                content TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_default INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # Status mappings table (for custom status subcategories)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS status_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status_name TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(status_name, subcategory)
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_scope ON chunks(scope)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_group_id ON chunks(group_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_documents_scope ON documents(scope)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_documents_group_id ON documents(group_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status_mappings_status ON status_mappings(status_name)')
        
        conn.commit()
    
    # ============ Document Operations ============
    
    async def add_document(self, name: str, raw_text: str, scope: str = 'global', 
                          group_id: Optional[str] = None) -> int:
        """Add a new document and return its ID"""
        return await self._run_in_executor(
            self._add_document, name, raw_text, scope, group_id
        )
    
    def _add_document(self, name: str, raw_text: str, scope: str, 
                     group_id: Optional[str]) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO documents (scope, group_id, name, created_at, raw_text, raw_text_len)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (scope, group_id, name, now, raw_text, len(raw_text)))
        conn.commit()
        return cursor.lastrowid
    
    async def get_documents(self, scope: Optional[str] = None, 
                           group_id: Optional[str] = None) -> List[Dict]:
        """Get documents filtered by scope and/or group_id"""
        return await self._run_in_executor(self._get_documents, scope, group_id)
    
    def _get_documents(self, scope: Optional[str], group_id: Optional[str]) -> List[Dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        query = 'SELECT * FROM documents WHERE 1=1'
        params = []
        
        if scope:
            query += ' AND scope = ?'
            params.append(scope)
        if group_id:
            query += ' AND group_id = ?'
            params.append(group_id)
        
        query += ' ORDER BY created_at DESC'
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    async def get_document_by_id(self, doc_id: int) -> Optional[Dict]:
        """Get a single document by ID"""
        return await self._run_in_executor(self._get_document_by_id, doc_id)
    
    def _get_document_by_id(self, doc_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM documents WHERE id = ?', (doc_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    async def delete_document(self, doc_id: int):
        """Delete a document and its chunks"""
        await self._run_in_executor(self._delete_document, doc_id)
    
    def _delete_document(self, doc_id: int):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM chunks WHERE doc_id = ?', (doc_id,))
        cursor.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
        conn.commit()
    
    async def clear_documents(self, scope: Optional[str] = None, 
                             group_id: Optional[str] = None):
        """Clear documents by scope/group"""
        await self._run_in_executor(self._clear_documents, scope, group_id)
    
    def _clear_documents(self, scope: Optional[str], group_id: Optional[str]):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Build WHERE clause
        conditions = []
        params = []
        if scope:
            conditions.append('scope = ?')
            params.append(scope)
        if group_id:
            conditions.append('group_id = ?')
            params.append(group_id)
        
        where_clause = ' AND '.join(conditions) if conditions else '1=1'
        
        # Get doc IDs to delete
        cursor.execute(f'SELECT id FROM documents WHERE {where_clause}', params)
        doc_ids = [row['id'] for row in cursor.fetchall()]
        
        if doc_ids:
            placeholders = ','.join('?' * len(doc_ids))
            cursor.execute(f'DELETE FROM chunks WHERE doc_id IN ({placeholders})', doc_ids)
            cursor.execute(f'DELETE FROM documents WHERE {where_clause}', params)
        
        conn.commit()
    
    # ============ Chunk Operations ============
    
    async def add_chunks(self, doc_id: int, chunks: List[Dict], scope: str = 'global',
                        group_id: Optional[str] = None):
        """Add multiple chunks for a document"""
        await self._run_in_executor(self._add_chunks, doc_id, chunks, scope, group_id)
    
    def _add_chunks(self, doc_id: int, chunks: List[Dict], scope: str,
                   group_id: Optional[str]):
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        for i, chunk in enumerate(chunks):
            cursor.execute('''
                INSERT INTO chunks (doc_id, scope, group_id, chunk_index, content, 
                                   tags_json, entities_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                doc_id,
                scope,
                group_id,
                i,
                chunk['content'],
                json.dumps(chunk.get('tags', []), ensure_ascii=False),
                json.dumps(chunk.get('entities', {}), ensure_ascii=False),
                now
            ))
        
        conn.commit()
    
    async def get_chunks(self, scope: Optional[str] = None, 
                        group_id: Optional[str] = None,
                        doc_id: Optional[int] = None) -> List[Dict]:
        """Get chunks with optional filters"""
        return await self._run_in_executor(self._get_chunks, scope, group_id, doc_id)
    
    def _get_chunks(self, scope: Optional[str], group_id: Optional[str],
                   doc_id: Optional[int]) -> List[Dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        query = 'SELECT * FROM chunks WHERE 1=1'
        params = []
        
        if scope:
            query += ' AND scope = ?'
            params.append(scope)
        if group_id:
            query += ' AND group_id = ?'
            params.append(group_id)
        if doc_id:
            query += ' AND doc_id = ?'
            params.append(doc_id)
        
        query += ' ORDER BY doc_id, chunk_index'
        cursor.execute(query, params)
        
        results = []
        for row in cursor.fetchall():
            chunk = dict(row)
            chunk['tags'] = json.loads(chunk['tags_json'])
            chunk['entities'] = json.loads(chunk['entities_json'])
            results.append(chunk)
        
        return results
    
    async def get_all_chunks_for_search(self, group_id: Optional[str] = None) -> List[Dict]:
        """Get all searchable chunks (global + group-specific)"""
        return await self._run_in_executor(self._get_all_chunks_for_search, group_id)
    
    def _get_all_chunks_for_search(self, group_id: Optional[str]) -> List[Dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Get global chunks
        query = "SELECT * FROM chunks WHERE scope = 'global'"
        cursor.execute(query)
        chunks = [dict(row) for row in cursor.fetchall()]
        
        # Get group-specific chunks if group_id provided
        if group_id:
            cursor.execute(
                "SELECT * FROM chunks WHERE scope = 'group' AND group_id = ?",
                (group_id,)
            )
            chunks.extend([dict(row) for row in cursor.fetchall()])
        
        # Parse JSON fields
        for chunk in chunks:
            chunk['tags'] = json.loads(chunk['tags_json'])
            chunk['entities'] = json.loads(chunk['entities_json'])
        
        return chunks
    
    async def get_chunk_count(self, scope: Optional[str] = None,
                             group_id: Optional[str] = None) -> int:
        """Get total chunk count"""
        return await self._run_in_executor(self._get_chunk_count, scope, group_id)
    
    def _get_chunk_count(self, scope: Optional[str], group_id: Optional[str]) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        query = 'SELECT COUNT(*) as cnt FROM chunks WHERE 1=1'
        params = []
        
        if scope:
            query += ' AND scope = ?'
            params.append(scope)
        if group_id:
            query += ' AND group_id = ?'
            params.append(group_id)
        
        cursor.execute(query, params)
        return cursor.fetchone()['cnt']
    
    # ============ Alias Operations ============
    
    async def add_alias(self, alias: str, canonical: str, 
                       alias_type: str = 'other') -> bool:
        """Add or update an alias"""
        return await self._run_in_executor(self._add_alias, alias, canonical, alias_type)
    
    def _add_alias(self, alias: str, canonical: str, alias_type: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT OR REPLACE INTO aliases (alias, canonical, type, created_at)
            VALUES (?, ?, ?, ?)
        ''', (alias.lower(), canonical, alias_type, now))
        conn.commit()
        return True
    
    async def get_aliases(self) -> List[Dict]:
        """Get all aliases"""
        return await self._run_in_executor(self._get_aliases)
    
    def _get_aliases(self) -> List[Dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM aliases ORDER BY alias')
        return [dict(row) for row in cursor.fetchall()]
    
    async def get_alias_map(self) -> Dict[str, str]:
        """Get alias -> canonical mapping"""
        return await self._run_in_executor(self._get_alias_map)
    
    def _get_alias_map(self) -> Dict[str, str]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT alias, canonical FROM aliases')
        return {row['alias']: row['canonical'] for row in cursor.fetchall()}
    
    async def delete_alias(self, alias: str) -> bool:
        """Delete an alias"""
        return await self._run_in_executor(self._delete_alias, alias)
    
    def _delete_alias(self, alias: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM aliases WHERE alias = ?', (alias.lower(),))
        conn.commit()
        return cursor.rowcount > 0
    
    # ============ Group Settings Operations ============
    
    async def get_group_settings(self, group_id: str) -> Dict:
        """Get or create group settings"""
        return await self._run_in_executor(self._get_group_settings, group_id)
    
    def _get_group_settings(self, group_id: str) -> Dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM group_settings WHERE group_id = ?', (group_id,))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        else:
            # Create default settings
            now = datetime.now().isoformat()
            cursor.execute('''
                INSERT INTO group_settings (group_id, default_mode, created_at)
                VALUES (?, 'simple', ?)
            ''', (group_id, now))
            conn.commit()
            return {
                'group_id': group_id,
                'default_mode': 'simple',
                'last_import_at': None,
                'created_at': now
            }
    
    async def update_group_settings(self, group_id: str, **kwargs):
        """Update group settings"""
        await self._run_in_executor(self._update_group_settings, group_id, kwargs)
    
    def _update_group_settings(self, group_id: str, updates: Dict):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Ensure record exists
        self._get_group_settings(group_id)
        
        # Build update query
        set_parts = []
        params = []
        for key, value in updates.items():
            if key in ('default_mode', 'last_import_at'):
                set_parts.append(f'{key} = ?')
                params.append(value)
        
        if set_parts:
            query = f"UPDATE group_settings SET {', '.join(set_parts)} WHERE group_id = ?"
            params.append(group_id)
            cursor.execute(query, params)
            conn.commit()
    
    # ============ Statistics ============
    
    async def get_stats(self, group_id: Optional[str] = None) -> Dict:
        """Get knowledge base statistics"""
        return await self._run_in_executor(self._get_stats, group_id)
    
    def _get_stats(self, group_id: Optional[str]) -> Dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        stats = {
            'global': {'doc_count': 0, 'chunk_count': 0},
            'group': {'doc_count': 0, 'chunk_count': 0},
            'total': {'doc_count': 0, 'chunk_count': 0}
        }
        
        # Global stats
        cursor.execute("SELECT COUNT(*) as cnt FROM documents WHERE scope = 'global'")
        stats['global']['doc_count'] = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) as cnt FROM chunks WHERE scope = 'global'")
        stats['global']['chunk_count'] = cursor.fetchone()['cnt']
        
        # Group stats (if group_id provided)
        if group_id:
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM documents WHERE scope = 'group' AND group_id = ?",
                (group_id,)
            )
            stats['group']['doc_count'] = cursor.fetchone()['cnt']
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM chunks WHERE scope = 'group' AND group_id = ?",
                (group_id,)
            )
            stats['group']['chunk_count'] = cursor.fetchone()['cnt']
        
        stats['total']['doc_count'] = stats['global']['doc_count'] + stats['group']['doc_count']
        stats['total']['chunk_count'] = stats['global']['chunk_count'] + stats['group']['chunk_count']
        
        return stats
    
    async def get_all_group_ids(self) -> List[str]:
        """Get all group IDs that have documents"""
        return await self._run_in_executor(self._get_all_group_ids)
    
    def _get_all_group_ids(self) -> List[str]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT group_id FROM documents WHERE group_id IS NOT NULL"
        )
        return [row['group_id'] for row in cursor.fetchall()]
    
    async def close(self):
        """Close database connection"""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._executor.shutdown(wait=True, cancel_futures=False)
    
    # ============ Custom Template Operations ============
    
    async def get_templates(self) -> List[Dict]:
        """Get all custom templates"""
        return await self._run_in_executor(self._get_templates)
    
    def _get_templates(self) -> List[Dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM custom_templates ORDER BY is_default DESC, name ASC')
        return [dict(row) for row in cursor.fetchall()]
    
    async def get_template_by_name(self, name: str) -> Optional[Dict]:
        """Get a template by name"""
        return await self._run_in_executor(self._get_template_by_name, name)
    
    def _get_template_by_name(self, name: str) -> Optional[Dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM custom_templates WHERE name = ?', (name,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    async def save_template(self, name: str, content: str, 
                           description: str = '', is_default: bool = False) -> int:
        """Save or update a custom template"""
        return await self._run_in_executor(
            self._save_template, name, content, description, is_default
        )
    
    def _save_template(self, name: str, content: str, 
                      description: str, is_default: bool) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        # Check if template exists
        cursor.execute('SELECT id FROM custom_templates WHERE name = ?', (name,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('''
                UPDATE custom_templates 
                SET content = ?, description = ?, is_default = ?, updated_at = ?
                WHERE name = ?
            ''', (content, description, 1 if is_default else 0, now, name))
            return existing['id']
        else:
            cursor.execute('''
                INSERT INTO custom_templates (name, content, description, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, content, description, 1 if is_default else 0, now, now))
            conn.commit()
            return cursor.lastrowid
    
    async def delete_template(self, name: str) -> bool:
        """Delete a custom template"""
        return await self._run_in_executor(self._delete_template, name)
    
    def _delete_template(self, name: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM custom_templates WHERE name = ?', (name,))
        conn.commit()
        return cursor.rowcount > 0
    
    # ============ Status Mapping Operations ============
    
    async def get_status_mappings(self, status_name: Optional[str] = None) -> List[Dict]:
        """Get status mappings, optionally filtered by status name"""
        return await self._run_in_executor(self._get_status_mappings, status_name)
    
    def _get_status_mappings(self, status_name: Optional[str]) -> List[Dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        if status_name:
            cursor.execute(
                'SELECT * FROM status_mappings WHERE status_name = ? ORDER BY subcategory',
                (status_name,)
            )
        else:
            cursor.execute('SELECT * FROM status_mappings ORDER BY status_name, subcategory')
        
        return [dict(row) for row in cursor.fetchall()]
    
    async def add_status_mapping(self, status_name: str, subcategory: str,
                                 display_name: str, description: str = '') -> int:
        """Add or update a status mapping"""
        return await self._run_in_executor(
            self._add_status_mapping, status_name, subcategory, display_name, description
        )
    
    def _add_status_mapping(self, status_name: str, subcategory: str,
                           display_name: str, description: str) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT OR REPLACE INTO status_mappings 
            (status_name, subcategory, display_name, description, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (status_name, subcategory, display_name, description, now))
        conn.commit()
        return cursor.lastrowid
    
    async def delete_status_mapping(self, mapping_id: int) -> bool:
        """Delete a status mapping by ID"""
        return await self._run_in_executor(self._delete_status_mapping, mapping_id)
    
    def _delete_status_mapping(self, mapping_id: int) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM status_mappings WHERE id = ?', (mapping_id,))
        conn.commit()
        return cursor.rowcount > 0
    
    async def get_status_mapping_dict(self) -> Dict[str, List[Dict]]:
        """Get all status mappings grouped by status name"""
        return await self._run_in_executor(self._get_status_mapping_dict)
    
    def _get_status_mapping_dict(self) -> Dict[str, List[Dict]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM status_mappings ORDER BY status_name, subcategory')
        
        result = {}
        for row in cursor.fetchall():
            mapping = dict(row)
            status_name = mapping['status_name']
            if status_name not in result:
                result[status_name] = []
            result[status_name].append(mapping)
        
        return result
