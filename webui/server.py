"""
WebUI Server for Limbus Guide Plugin
Provides REST API and simple HTML interface for knowledge base management
"""
import os
import asyncio
import secrets
import socket
from typing import Optional, Callable, Awaitable
from datetime import datetime


def _check_port_available(host: str, port: int) -> bool:
    """Check if a port is available for binding"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            # For 0.0.0.0, we check localhost since that's what matters for conflicts
            check_host = '127.0.0.1' if host == '0.0.0.0' else host
            sock.bind((check_host, port))
            return True
    except OSError:
        return False


# Delay in seconds to wait for server startup before checking status
_SERVER_STARTUP_CHECK_DELAY = 0.5


class WebUIServer:
    """FastAPI-based WebUI server for knowledge base management"""
    
    def __init__(self, 
                 db,  # Database instance
                 chunker,  # Chunker instance
                 tagger,  # Tagger instance
                 searcher,  # Searcher instance
                 config: dict,
                 on_index_update: Optional[Callable[[], Awaitable[None]]] = None):
        """
        Initialize WebUI server
        
        Args:
            db: Database instance
            chunker: Chunker instance
            tagger: Tagger instance
            searcher: Searcher instance
            config: Configuration dict with webui settings
            on_index_update: Callback to rebuild search index after data changes
        """
        self.db = db
        self.chunker = chunker
        self.tagger = tagger
        self.searcher = searcher
        self.config = config
        self.on_index_update = on_index_update
        
        self.host = config.get('webui_host', '0.0.0.0')
        self.port = config.get('webui_port', 8765)
        self.token = config.get('webui_token') or self._generate_token()
        self.enabled = config.get('webui_enabled', True)
        
        self.app = None
        self.server = None
        self._server_task = None
    
    def _generate_token(self) -> str:
        """Generate a secure random token"""
        return secrets.token_urlsafe(32)
    
    def get_token(self) -> str:
        """Get the current authentication token"""
        return self.token
    
    def get_url(self) -> str:
        """Get the WebUI URL"""
        return f"http://{self.host}:{self.port}"
    
    async def start(self):
        """Start the WebUI server
        
        Raises:
            RuntimeError: If the port is not available or server fails to start
        """
        if not self.enabled:
            return
        
        try:
            from fastapi import FastAPI, HTTPException, Depends, Request, File, UploadFile, Form
            from fastapi.responses import HTMLResponse, JSONResponse
            from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
            from pydantic import BaseModel
            import uvicorn
        except ImportError:
            # FastAPI not available, skip WebUI
            raise RuntimeError(
                "WebUI 依赖未安装。请运行: pip install fastapi uvicorn python-multipart"
            )
        
        # Check if port is available before starting
        if not _check_port_available(self.host, self.port):
            raise RuntimeError(
                f"端口 {self.port} 已被占用。请在配置中更改 webui_port，"
                f"或检查是否有其他服务正在使用该端口。"
            )
        
        app = FastAPI(title="Limbus Guide WebUI", version="1.0.0")
        security = HTTPBearer(auto_error=False)
        
        # Token verification
        async def verify_token(
            request: Request,
            credentials: HTTPAuthorizationCredentials = Depends(security)
        ):
            # Check header token
            if credentials and credentials.credentials == self.token:
                return True
            
            # Check query parameter token
            token_param = request.query_params.get('token')
            if token_param == self.token:
                return True
            
            raise HTTPException(status_code=401, detail="Invalid or missing token")
        
        # Request models
        class SearchRequest(BaseModel):
            query: str
            group_id: Optional[str] = None
            top_k: int = 6
        
        class AliasRequest(BaseModel):
            alias: str
            canonical: str
            type: str = 'other'
        
        # ============ HTML Pages ============
        
        @app.get("/", response_class=HTMLResponse)
        async def index_page(request: Request, _=Depends(verify_token)):
            """Main status page"""
            stats = await self.db.get_stats()
            group_ids = await self.db.get_all_group_ids()
            
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Limbus Guide WebUI</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .card {{ background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 8px; }}
        .stat {{ display: inline-block; margin: 10px 20px 10px 0; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #333; }}
        .stat-label {{ color: #666; }}
        nav {{ margin-bottom: 20px; }}
        nav a {{ margin-right: 15px; text-decoration: none; color: #0066cc; }}
        nav a:hover {{ text-decoration: underline; }}
        h1 {{ color: #333; }}
        .warning {{ background: #fff3cd; border: 1px solid #ffc107; padding: 10px; border-radius: 4px; margin: 10px 0; }}
    </style>
</head>
<body>
    <h1>📚 Limbus Guide WebUI</h1>
    
    <nav>
        <a href="/?token={self.token}">状态</a>
        <a href="/docs-page?token={self.token}">文档管理</a>
        <a href="/chunks-page?token={self.token}">Chunk浏览</a>
        <a href="/search-page?token={self.token}">检索调试</a>
        <a href="/aliases-page?token={self.token}">别名词典</a>
    </nav>
    
    <div class="warning">
        ⚠️ <strong>安全提示</strong>：请勿泄露URL中的token。建议使用Nginx反代并启用HTTPS。
    </div>
    
    <div class="card">
        <h2>运行状态</h2>
        <div class="stat">
            <div class="stat-value">✅ 运行中</div>
            <div class="stat-label">服务状态</div>
        </div>
        <div class="stat">
            <div class="stat-value">{self.host}:{self.port}</div>
            <div class="stat-label">监听地址</div>
        </div>
    </div>
    
    <div class="card">
        <h2>知识库统计</h2>
        <div class="stat">
            <div class="stat-value">{stats['global']['doc_count']}</div>
            <div class="stat-label">全局文档</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats['global']['chunk_count']}</div>
            <div class="stat-label">全局Chunks</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(group_ids)}</div>
            <div class="stat-label">群组数量</div>
        </div>
    </div>
    
    <div class="card">
        <h2>配置信息</h2>
        <p>TopK: {self.config.get('top_k', 6)}</p>
        <p>Chunk大小: {self.config.get('chunk_size', 800)}</p>
        <p>重叠: {self.config.get('overlap', 120)}</p>
        <p>群覆盖加权: {self.config.get('group_boost', 1.2)}</p>
    </div>
    
    <div class="card">
        <h2>群组列表</h2>
        {'<p>暂无群组数据</p>' if not group_ids else '<ul>' + ''.join(f'<li>{gid}</li>' for gid in group_ids) + '</ul>'}
    </div>
</body>
</html>
"""
            return HTMLResponse(content=html)
        
        @app.get("/docs-page", response_class=HTMLResponse)
        async def docs_page(request: Request, _=Depends(verify_token)):
            """Document management page"""
            global_docs = await self.db.get_documents(scope='global')
            group_docs = await self.db.get_documents(scope='group')
            
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>文档管理 - Limbus Guide</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .card {{ background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 8px; }}
        nav {{ margin-bottom: 20px; }}
        nav a {{ margin-right: 15px; text-decoration: none; color: #0066cc; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #e0e0e0; }}
        .btn {{ padding: 5px 10px; margin: 2px; cursor: pointer; border: none; border-radius: 4px; }}
        .btn-danger {{ background: #dc3545; color: white; }}
        .btn-primary {{ background: #007bff; color: white; }}
        form {{ margin: 10px 0; }}
        input, select {{ padding: 8px; margin: 5px 0; }}
        .tabs {{ display: flex; border-bottom: 2px solid #ddd; margin-bottom: 15px; }}
        .tab {{ padding: 10px 20px; cursor: pointer; border: none; background: none; }}
        .tab.active {{ border-bottom: 2px solid #007bff; color: #007bff; }}
    </style>
</head>
<body>
    <h1>📄 文档管理</h1>
    
    <nav>
        <a href="/?token={self.token}">状态</a>
        <a href="/docs-page?token={self.token}">文档管理</a>
        <a href="/chunks-page?token={self.token}">Chunk浏览</a>
        <a href="/search-page?token={self.token}">检索调试</a>
        <a href="/aliases-page?token={self.token}">别名词典</a>
    </nav>
    
    <div class="card">
        <h2>上传文档</h2>
        <form id="uploadForm" enctype="multipart/form-data">
            <div>
                <label>文件：</label>
                <input type="file" name="file" accept=".txt,.md" required>
            </div>
            <div>
                <label>范围：</label>
                <select name="scope" id="scopeSelect">
                    <option value="global">全局库</option>
                    <option value="group">群覆盖库</option>
                </select>
            </div>
            <div id="groupIdDiv" style="display:none;">
                <label>群号：</label>
                <input type="text" name="group_id" placeholder="请输入群号">
            </div>
            <button type="submit" class="btn btn-primary">上传</button>
        </form>
    </div>
    
    <div class="card">
        <h2>全局库文档 ({len(global_docs)})</h2>
        <table>
            <tr><th>ID</th><th>文档名</th><th>字符数</th><th>创建时间</th><th>操作</th></tr>
            {''.join(f'''<tr>
                <td>{doc['id']}</td>
                <td>{doc['name']}</td>
                <td>{doc['raw_text_len']}</td>
                <td>{doc['created_at'][:19]}</td>
                <td><button class="btn btn-danger" onclick="deleteDoc({doc['id']})">删除</button></td>
            </tr>''' for doc in global_docs) or '<tr><td colspan="5">暂无文档</td></tr>'}
        </table>
        <button class="btn btn-danger" onclick="clearGlobal()" style="margin-top:10px;">清空全局库</button>
    </div>
    
    <div class="card">
        <h2>群覆盖库文档 ({len(group_docs)})</h2>
        <table>
            <tr><th>ID</th><th>文档名</th><th>群号</th><th>字符数</th><th>创建时间</th><th>操作</th></tr>
            {''.join(f'''<tr>
                <td>{doc['id']}</td>
                <td>{doc['name']}</td>
                <td>{doc['group_id']}</td>
                <td>{doc['raw_text_len']}</td>
                <td>{doc['created_at'][:19]}</td>
                <td><button class="btn btn-danger" onclick="deleteDoc({doc['id']})">删除</button></td>
            </tr>''' for doc in group_docs) or '<tr><td colspan="6">暂无文档</td></tr>'}
        </table>
    </div>
    
    <script>
        const token = '{self.token}';
        
        document.getElementById('scopeSelect').onchange = function() {{
            document.getElementById('groupIdDiv').style.display = 
                this.value === 'group' ? 'block' : 'none';
        }};
        
        document.getElementById('uploadForm').onsubmit = async function(e) {{
            e.preventDefault();
            const formData = new FormData(this);
            try {{
                const resp = await fetch('/docs/upload?token=' + token, {{
                    method: 'POST',
                    body: formData
                }});
                const data = await resp.json();
                if (resp.ok) {{
                    alert('上传成功！');
                    location.reload();
                }} else {{
                    alert('上传失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('上传失败：' + err.message);
            }}
        }};
        
        async function deleteDoc(docId) {{
            if (!confirm('确定要删除这个文档吗？')) return;
            try {{
                const resp = await fetch('/docs/' + docId + '?token=' + token, {{
                    method: 'DELETE'
                }});
                if (resp.ok) {{
                    location.reload();
                }} else {{
                    const data = await resp.json();
                    alert('删除失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('删除失败：' + err.message);
            }}
        }}
        
        async function clearGlobal() {{
            if (!confirm('确定要清空整个全局库吗？此操作不可恢复！')) return;
            if (!confirm('再次确认：真的要清空全局库吗？')) return;
            try {{
                const resp = await fetch('/docs/clear?scope=global&token=' + token, {{
                    method: 'DELETE'
                }});
                if (resp.ok) {{
                    location.reload();
                }} else {{
                    const data = await resp.json();
                    alert('清空失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('清空失败：' + err.message);
            }}
        }}
    </script>
</body>
</html>
"""
            return HTMLResponse(content=html)
        
        @app.get("/chunks-page", response_class=HTMLResponse)
        async def chunks_page(
            request: Request,
            group_id: Optional[str] = None,
            doc_id: Optional[int] = None,
            _=Depends(verify_token)
        ):
            """Chunk browsing page"""
            chunks = await self.db.get_chunks(group_id=group_id, doc_id=doc_id)
            chunks = chunks[:100]  # Limit to 100 for display
            
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Chunk浏览 - Limbus Guide</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .card {{ background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 8px; }}
        nav {{ margin-bottom: 20px; }}
        nav a {{ margin-right: 15px; text-decoration: none; color: #0066cc; }}
        .chunk {{ border: 1px solid #ddd; margin: 10px 0; padding: 10px; background: white; border-radius: 4px; }}
        .chunk-header {{ font-weight: bold; color: #333; margin-bottom: 5px; }}
        .chunk-tags {{ color: #666; font-size: 12px; margin: 5px 0; }}
        .chunk-content {{ white-space: pre-wrap; font-size: 14px; max-height: 200px; overflow-y: auto; }}
        .tag {{ display: inline-block; background: #e0e0e0; padding: 2px 8px; margin: 2px; border-radius: 10px; font-size: 11px; }}
        form {{ margin: 10px 0; }}
        input, select {{ padding: 8px; margin: 5px; }}
        .btn {{ padding: 8px 15px; cursor: pointer; border: none; border-radius: 4px; background: #007bff; color: white; }}
    </style>
</head>
<body>
    <h1>📦 Chunk浏览</h1>
    
    <nav>
        <a href="/?token={self.token}">状态</a>
        <a href="/docs-page?token={self.token}">文档管理</a>
        <a href="/chunks-page?token={self.token}">Chunk浏览</a>
        <a href="/search-page?token={self.token}">检索调试</a>
        <a href="/aliases-page?token={self.token}">别名词典</a>
    </nav>
    
    <div class="card">
        <h2>筛选条件</h2>
        <form method="get">
            <input type="hidden" name="token" value="{self.token}">
            <input type="text" name="group_id" placeholder="群号" value="{group_id or ''}">
            <input type="number" name="doc_id" placeholder="文档ID" value="{doc_id or ''}">
            <button type="submit" class="btn">筛选</button>
        </form>
    </div>
    
    <div class="card">
        <h2>Chunks (显示前100条，共{len(chunks)}条)</h2>
        {''.join(f'''
        <div class="chunk">
            <div class="chunk-header">
                Chunk #{chunk['id']} | Doc #{chunk['doc_id']} | 
                {chunk['scope']} | {chunk.get('group_id', '-')}
            </div>
            <div class="chunk-tags">
                {''.join(f'<span class="tag">{tag}</span>' for tag in chunk.get('tags', []))}
            </div>
            <div class="chunk-content">{chunk['content'][:500]}{'...' if len(chunk['content']) > 500 else ''}</div>
        </div>
        ''' for chunk in chunks) or '<p>暂无Chunks</p>'}
    </div>
</body>
</html>
"""
            return HTMLResponse(content=html)
        
        @app.get("/search-page", response_class=HTMLResponse)
        async def search_page(request: Request, _=Depends(verify_token)):
            """Search debugging page"""
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>检索调试 - Limbus Guide</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .card {{ background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 8px; }}
        nav {{ margin-bottom: 20px; }}
        nav a {{ margin-right: 15px; text-decoration: none; color: #0066cc; }}
        .result {{ border: 1px solid #ddd; margin: 10px 0; padding: 10px; background: white; border-radius: 4px; }}
        .result-header {{ font-weight: bold; color: #333; }}
        .score {{ color: #28a745; font-weight: bold; }}
        .breakdown {{ color: #666; font-size: 12px; }}
        .content {{ white-space: pre-wrap; font-size: 14px; margin-top: 10px; max-height: 150px; overflow-y: auto; }}
        .tag {{ display: inline-block; background: #e0e0e0; padding: 2px 8px; margin: 2px; border-radius: 10px; font-size: 11px; }}
        .tag.matched {{ background: #28a745; color: white; }}
        form {{ margin: 10px 0; }}
        input, select {{ padding: 8px; margin: 5px; width: 300px; }}
        .btn {{ padding: 8px 15px; cursor: pointer; border: none; border-radius: 4px; background: #007bff; color: white; }}
        #results {{ display: none; }}
        .query-info {{ background: #e8f4f8; padding: 10px; border-radius: 4px; margin: 10px 0; }}
    </style>
</head>
<body>
    <h1>🔍 检索调试</h1>
    
    <nav>
        <a href="/?token={self.token}">状态</a>
        <a href="/docs-page?token={self.token}">文档管理</a>
        <a href="/chunks-page?token={self.token}">Chunk浏览</a>
        <a href="/search-page?token={self.token}">检索调试</a>
        <a href="/aliases-page?token={self.token}">别名词典</a>
    </nav>
    
    <div class="card">
        <h2>搜索</h2>
        <form id="searchForm">
            <div>
                <input type="text" id="query" placeholder="输入问题..." required>
            </div>
            <div>
                <input type="text" id="groupId" placeholder="群号（可选）">
            </div>
            <div>
                <input type="number" id="topK" value="6" min="1" max="20" style="width:80px;">
                <label>TopK</label>
            </div>
            <button type="submit" class="btn">搜索</button>
        </form>
    </div>
    
    <div id="results" class="card">
        <h2>搜索结果</h2>
        <div id="queryInfo" class="query-info"></div>
        <div id="resultsList"></div>
    </div>
    
    <script>
        const token = '{self.token}';
        
        document.getElementById('searchForm').onsubmit = async function(e) {{
            e.preventDefault();
            const query = document.getElementById('query').value;
            const groupId = document.getElementById('groupId').value;
            const topK = parseInt(document.getElementById('topK').value);
            
            try {{
                const resp = await fetch('/search?token=' + token, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{query, group_id: groupId || null, top_k: topK}})
                }});
                const data = await resp.json();
                
                document.getElementById('results').style.display = 'block';
                
                // Query info
                const info = data.query_info || {{}};
                document.getElementById('queryInfo').innerHTML = `
                    <strong>查询分析：</strong><br>
                    原始查询: ${{info.original_query || query}}<br>
                    处理后: ${{info.processed_query || query}}<br>
                    提取标签: ${{(info.extracted_tags || []).join(', ') || '无'}}<br>
                    别名替换: ${{(info.alias_substitutions || []).join(', ') || '无'}}
                `;
                
                // Results
                const results = data.results || [];
                if (results.length === 0) {{
                    document.getElementById('resultsList').innerHTML = '<p>无匹配结果</p>';
                }} else {{
                    document.getElementById('resultsList').innerHTML = results.map((r, i) => `
                        <div class="result">
                            <div class="result-header">
                                #${{i+1}} | Chunk ${{r.id}} | 
                                ${{r.scope}} ${{r.group_id ? '(' + r.group_id + ')' : ''}}
                                <span class="score">得分: ${{r.score.toFixed(3)}}</span>
                            </div>
                            <div class="breakdown">
                                BM25: ${{r.score_breakdown?.bm25?.toFixed(3) || 0}} |
                                标签加权: ${{r.score_breakdown?.tag_boost?.toFixed(3) || 0}} |
                                群加权: ${{r.score_breakdown?.group_boost?.toFixed(3) || 0}}
                            </div>
                            <div>
                                ${{(r.tags || []).map(t => 
                                    `<span class="tag ${{(r.score_breakdown?.matching_tags || []).includes(t) ? 'matched' : ''}}">${{t}}</span>`
                                ).join('')}}
                            </div>
                            <div class="content">${{r.content.substring(0, 400)}}${{r.content.length > 400 ? '...' : ''}}</div>
                        </div>
                    `).join('');
                }}
            }} catch (err) {{
                alert('搜索失败：' + err.message);
            }}
        }};
    </script>
</body>
</html>
"""
            return HTMLResponse(content=html)
        
        @app.get("/aliases-page", response_class=HTMLResponse)
        async def aliases_page(request: Request, _=Depends(verify_token)):
            """Alias management page"""
            aliases = await self.db.get_aliases()
            
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>别名词典 - Limbus Guide</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .card {{ background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 8px; }}
        nav {{ margin-bottom: 20px; }}
        nav a {{ margin-right: 15px; text-decoration: none; color: #0066cc; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #e0e0e0; }}
        .btn {{ padding: 5px 10px; cursor: pointer; border: none; border-radius: 4px; }}
        .btn-danger {{ background: #dc3545; color: white; }}
        .btn-primary {{ background: #007bff; color: white; }}
        form {{ margin: 10px 0; }}
        input, select {{ padding: 8px; margin: 5px 0; }}
    </style>
</head>
<body>
    <h1>📝 别名词典</h1>
    
    <nav>
        <a href="/?token={self.token}">状态</a>
        <a href="/docs-page?token={self.token}">文档管理</a>
        <a href="/chunks-page?token={self.token}">Chunk浏览</a>
        <a href="/search-page?token={self.token}">检索调试</a>
        <a href="/aliases-page?token={self.token}">别名词典</a>
    </nav>
    
    <div class="card">
        <h2>添加别名</h2>
        <form id="aliasForm">
            <div>
                <label>别名：</label>
                <input type="text" id="alias" placeholder="例如：红叔" required>
            </div>
            <div>
                <label>标准名：</label>
                <input type="text" id="canonical" placeholder="例如：洪鹿" required>
            </div>
            <div>
                <label>类型：</label>
                <select id="aliasType">
                    <option value="identity">人格</option>
                    <option value="ego">EGO</option>
                    <option value="status">状态</option>
                    <option value="mode">模式</option>
                    <option value="other" selected>其他</option>
                </select>
            </div>
            <button type="submit" class="btn btn-primary">添加</button>
        </form>
    </div>
    
    <div class="card">
        <h2>别名列表 ({len(aliases)})</h2>
        <table>
            <tr><th>别名</th><th>标准名</th><th>类型</th><th>创建时间</th><th>操作</th></tr>
            {''.join(f'''<tr>
                <td>{a['alias']}</td>
                <td>{a['canonical']}</td>
                <td>{a['type']}</td>
                <td>{a['created_at'][:19]}</td>
                <td><button class="btn btn-danger" onclick="deleteAlias('{a['alias']}')">删除</button></td>
            </tr>''' for a in aliases) or '<tr><td colspan="5">暂无别名</td></tr>'}
        </table>
    </div>
    
    <script>
        const token = '{self.token}';
        
        document.getElementById('aliasForm').onsubmit = async function(e) {{
            e.preventDefault();
            const alias = document.getElementById('alias').value;
            const canonical = document.getElementById('canonical').value;
            const type = document.getElementById('aliasType').value;
            
            try {{
                const resp = await fetch('/aliases?token=' + token, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{alias, canonical, type}})
                }});
                if (resp.ok) {{
                    location.reload();
                }} else {{
                    const data = await resp.json();
                    alert('添加失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('添加失败：' + err.message);
            }}
        }};
        
        async function deleteAlias(alias) {{
            if (!confirm('确定要删除这个别名吗？')) return;
            try {{
                const resp = await fetch('/aliases/' + encodeURIComponent(alias) + '?token=' + token, {{
                    method: 'DELETE'
                }});
                if (resp.ok) {{
                    location.reload();
                }} else {{
                    const data = await resp.json();
                    alert('删除失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('删除失败：' + err.message);
            }}
        }}
    </script>
</body>
</html>
"""
            return HTMLResponse(content=html)
        
        # ============ REST API ============
        
        @app.get("/docs")
        async def list_docs(
            scope: Optional[str] = None,
            group_id: Optional[str] = None,
            _=Depends(verify_token)
        ):
            """List documents"""
            docs = await self.db.get_documents(scope=scope, group_id=group_id)
            return {"documents": docs}
        
        @app.post("/docs/upload")
        async def upload_doc(
            file: UploadFile = File(...),
            scope: str = Form("global"),
            group_id: Optional[str] = Form(None),
            _=Depends(verify_token)
        ):
            """Upload a document"""
            # Read file content
            content = await file.read()
            try:
                text = content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    text = content.decode('gbk')
                except UnicodeDecodeError:
                    raise HTTPException(status_code=400, detail="无法解码文件，请使用UTF-8编码")
            
            if not text.strip():
                raise HTTPException(status_code=400, detail="文件内容为空")
            
            # Get filename
            filename = file.filename or f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Process document
            doc_id = await self.db.add_document(
                name=filename,
                raw_text=text,
                scope=scope,
                group_id=group_id if scope == 'group' else None
            )
            
            # Chunk and tag
            chunks = self.chunker.process_document(text, filename)
            chunks = self.tagger.process_chunks(chunks)
            
            # Save chunks
            await self.db.add_chunks(
                doc_id=doc_id,
                chunks=chunks,
                scope=scope,
                group_id=group_id if scope == 'group' else None
            )
            
            # Trigger index update
            if self.on_index_update:
                await self.on_index_update()
            
            return {
                "success": True,
                "doc_id": doc_id,
                "name": filename,
                "char_count": len(text),
                "chunk_count": len(chunks)
            }
        
        @app.delete("/docs/{doc_id}")
        async def delete_doc(doc_id: int, _=Depends(verify_token)):
            """Delete a document"""
            doc = await self.db.get_document_by_id(doc_id)
            if not doc:
                raise HTTPException(status_code=404, detail="文档不存在")
            
            await self.db.delete_document(doc_id)
            
            if self.on_index_update:
                await self.on_index_update()
            
            return {"success": True}
        
        @app.delete("/docs/clear")
        async def clear_docs(
            scope: Optional[str] = None,
            group_id: Optional[str] = None,
            _=Depends(verify_token)
        ):
            """Clear documents"""
            await self.db.clear_documents(scope=scope, group_id=group_id)
            
            if self.on_index_update:
                await self.on_index_update()
            
            return {"success": True}
        
        @app.get("/chunks")
        async def list_chunks(
            scope: Optional[str] = None,
            group_id: Optional[str] = None,
            doc_id: Optional[int] = None,
            _=Depends(verify_token)
        ):
            """List chunks"""
            chunks = await self.db.get_chunks(scope=scope, group_id=group_id, doc_id=doc_id)
            return {"chunks": chunks}
        
        @app.post("/search")
        async def search(request: SearchRequest, _=Depends(verify_token)):
            """Search chunks"""
            result = self.searcher.search_with_debug(
                query=request.query,
                top_k=request.top_k,
                group_id=request.group_id
            )
            return result
        
        @app.get("/aliases")
        async def list_aliases(_=Depends(verify_token)):
            """List all aliases"""
            aliases = await self.db.get_aliases()
            return {"aliases": aliases}
        
        @app.post("/aliases")
        async def add_alias(request: AliasRequest, _=Depends(verify_token)):
            """Add or update an alias"""
            await self.db.add_alias(
                alias=request.alias,
                canonical=request.canonical,
                alias_type=request.type
            )
            
            # Update searcher
            alias_map = await self.db.get_alias_map()
            self.searcher.update_aliases(alias_map)
            
            return {"success": True}
        
        @app.delete("/aliases/{alias}")
        async def delete_alias(alias: str, _=Depends(verify_token)):
            """Delete an alias"""
            success = await self.db.delete_alias(alias)
            if not success:
                raise HTTPException(status_code=404, detail="别名不存在")
            
            # Update searcher
            alias_map = await self.db.get_alias_map()
            self.searcher.update_aliases(alias_map)
            
            return {"success": True}
        
        @app.get("/stats")
        async def get_stats(group_id: Optional[str] = None, _=Depends(verify_token)):
            """Get knowledge base statistics"""
            stats = await self.db.get_stats(group_id)
            return stats
        
        self.app = app
        
        # Start server in background
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning"
        )
        self.server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(self.server.serve())
        
        # Wait a moment and check if server started successfully
        # The port check above should catch most issues, but we also
        # wait a bit to see if any startup errors occur
        await asyncio.sleep(_SERVER_STARTUP_CHECK_DELAY)
        
        # Check if the server task has already failed
        if self._server_task.done():
            try:
                self._server_task.result()
            except Exception as e:
                raise RuntimeError(f"WebUI 服务器启动失败: {e}")
        
        # Check if server actually started (uvicorn sets started=True after binding)
        if not getattr(self.server, 'started', False):
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
            raise RuntimeError(
                f"WebUI 服务器启动失败。请检查端口 {self.port} 是否可用。"
            )
    
    async def stop(self):
        """Stop the WebUI server"""
        if self.server:
            self.server.should_exit = True
            if self._server_task:
                try:
                    await asyncio.wait_for(self._server_task, timeout=5.0)
                except asyncio.TimeoutError:
                    self._server_task.cancel()
                    try:
                        await self._server_task
                    except asyncio.CancelledError:
                        pass  # Expected when task is cancelled
