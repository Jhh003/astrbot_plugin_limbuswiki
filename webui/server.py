# -*- coding: utf-8 -*-
"""
WebUI Server for Limbus Guide Plugin
Provides REST API and simple HTML interface for knowledge base management
"""
import os
import asyncio
import secrets
import socket
import json
from typing import Optional, Callable, Awaitable, List, Dict, Any
from datetime import datetime


def _render_global_doc_rows(docs: List[Dict[str, Any]]) -> str:
    """Render HTML table rows for global documents."""
    if not docs:
        return '<tr><td colspan="5" class="empty-row">暂无文档</td></tr>'
    rows = []
    for doc in docs:
        doc_id = doc['id']
        row = (
            '<tr>'
            '<td>' + str(doc_id) + '</td>'
            '<td>' + str(doc['name']) + '</td>'
            '<td>' + '{:,}'.format(doc['raw_text_len']) + '</td>'
            '<td>' + str(doc['created_at'][:19]) + '</td>'
            '<td><button class="btn btn-danger" onclick="deleteDoc(' + str(doc_id) + ')">&#128465;&#65039; 删除</button></td>'
            '</tr>'
        )
        rows.append(row)
    return ''.join(rows)


def _render_group_doc_rows(docs: List[Dict[str, Any]]) -> str:
    """Render HTML table rows for group documents."""
    if not docs:
        return '<tr><td colspan="6" class="empty-row">暂无文档</td></tr>'
    rows = []
    for doc in docs:
        doc_id = doc['id']
        row = (
            '<tr>'
            '<td>' + str(doc_id) + '</td>'
            '<td>' + str(doc['name']) + '</td>'
            '<td>' + str(doc['group_id']) + '</td>'
            '<td>' + '{:,}'.format(doc['raw_text_len']) + '</td>'
            '<td>' + str(doc['created_at'][:19]) + '</td>'
            '<td><button class="btn btn-danger" onclick="deleteDoc(' + str(doc_id) + ')">&#128465;&#65039; 删除</button></td>'
            '</tr>'
        )
        rows.append(row)
    return ''.join(rows)


def _render_group_tags(group_ids: List[str]) -> str:
    """Render HTML for group ID tags."""
    if not group_ids:
        return '<p class="empty-text">暂无群组数据</p>'
    tags = ''.join('<span class="group-tag">' + str(gid) + '</span>' for gid in group_ids)
    return '<div class="group-list">' + tags + '</div>'


def _render_chunk_tags(tags: List[str]) -> str:
    """Render HTML for chunk tags."""
    if not tags:
        return '<span style="color:#666;font-size:12px;">无标签</span>'
    return ''.join('<span class="tag">' + str(tag) + '</span>' for tag in tags)


def _render_chunks(chunks: List[Dict[str, Any]]) -> str:
    """Render HTML for chunk display."""
    if not chunks:
        return '<p class="empty-text">暂无分块数据</p>'
    result = []
    for chunk in chunks:
        scope_text = '&#127760; 全局' if chunk['scope'] == 'global' else '&#128101; 群组'
        group_id = chunk.get('group_id') or ''
        content = chunk['content']
        content_display = content[:500] + ('...' if len(content) > 500 else '')
        tags_html = _render_chunk_tags(chunk.get('tags', []))
        html = (
            '<div class="chunk">'
            '<div class="chunk-header">'
            '&#128290; 分块 #' + str(chunk['id']) + ' | &#128196; 文档 #' + str(chunk['doc_id']) + ' | ' +
            scope_text + ' ' + str(group_id) +
            '</div>'
            '<div class="chunk-tags">' + tags_html + '</div>'
            '<div class="chunk-content">' + content_display + '</div>'
            '</div>'
        )
        result.append(html)
    return ''.join(result)


def _render_alias_rows(aliases: List[Dict[str, Any]], type_display: Dict[str, str]) -> str:
    """Render HTML table rows for aliases."""
    if not aliases:
        return '<tr><td colspan="5" class="empty-row">暂无别名数据</td></tr>'
    rows = []
    for a in aliases:
        alias_val = a['alias']
        type_val = a['type']
        type_text = type_display.get(type_val, type_val)
        row = (
            '<tr>'
            '<td><strong>' + str(alias_val) + '</strong></td>'
            '<td>' + str(a['canonical']) + '</td>'
            '<td><span class="type-badge type-' + str(type_val) + '">' + type_text + '</span></td>'
            '<td>' + str(a['created_at'][:19]) + '</td>'
            "<td><button class=\"btn btn-danger\" onclick=\"deleteAlias('" + str(alias_val) + "')\">&#128465;&#65039; 删除</button></td>"
            '</tr>'
        )
        rows.append(row)
    return ''.join(rows)


def _render_nav(token: str, active: str = '') -> str:
    """Render navigation bar with active page highlighted."""
    nav_items = [
        ('/', '&#128202; 状态总览', 'status'),
        ('/docs-page', '&#128196; 文档管理', 'docs'),
        ('/chunks-page', '&#128230; 分块浏览', 'chunks'),
        ('/search-page', '&#128269; 检索调试', 'search'),
        ('/aliases-page', '&#128221; 别名词典', 'aliases'),
        ('/model-settings-page', '&#9881;&#65039; 模型设置', 'model'),
        ('/template-page', '&#128203; 文档模版', 'template'),
        ('/status-mapping-page', '&#127991;&#65039; 状态映射', 'mapping'),
    ]
    
    links = []
    for path, label, key in nav_items:
        active_class = ' class="active"' if key == active else ''
        links.append(f'<a href="{path}?token={token}"{active_class}>{label}</a>')
    
    return '<nav>\n            ' + '\n            '.join(links) + '\n        </nav>'


def _render_status_mapping_rows(mappings: List[Dict[str, Any]]) -> str:
    """Render HTML table rows for status mappings."""
    if not mappings:
        return '<tr><td colspan="5" class="empty-row">暂无状态映射数据</td></tr>'
    rows = []
    for m in mappings:
        row = (
            '<tr>'
            '<td><strong>' + str(m['status_name']) + '</strong></td>'
            '<td>' + str(m['subcategory']) + '</td>'
            '<td>' + str(m['display_name']) + '</td>'
            '<td>' + str(m.get('description', '') or '') + '</td>'
            '<td><button class="btn btn-danger" onclick="deleteMapping(' + str(m['id']) + ')">&#128465;&#65039; 删除</button></td>'
            '</tr>'
        )
        rows.append(row)
    return ''.join(rows)


def _render_template_rows(templates: List[Dict[str, Any]]) -> str:
    """Render HTML table rows for custom templates."""
    if not templates:
        return '<tr><td colspan="5" class="empty-row">暂无自定义模板</td></tr>'
    rows = []
    for t in templates:
        default_badge = '<span class="badge badge-default">默认</span>' if t.get('is_default') else ''
        row = (
            '<tr>'
            '<td><strong>' + str(t['name']) + '</strong> ' + default_badge + '</td>'
            '<td>' + str(t.get('description', '') or '') + '</td>'
            '<td>' + str(len(t.get('content', ''))) + ' 字符</td>'
            '<td>' + str(t['updated_at'][:19]) + '</td>'
            "<td>"
            "<button class=\"btn btn-primary btn-sm\" onclick=\"editTemplate('" + str(t['name']) + "')\">&#9998; 编辑</button> "
            "<button class=\"btn btn-danger btn-sm\" onclick=\"deleteTemplate('" + str(t['name']) + "')\">&#128465;&#65039; 删除</button>"
            "</td>"
            '</tr>'
        )
        rows.append(row)
    return ''.join(rows)


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
<html lang="zh-CN">
<head>
    <title>边狱巴士攻略管理</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(90deg, #e94560 0%, #ff6b6b 100%);
            padding: 30px;
            border-radius: 16px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(233, 69, 96, 0.3);
        }}
        .header h1 {{ 
            color: #fff; 
            font-size: 28px; 
            font-weight: 700;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }}
        nav {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        nav a {{
            color: #e0e0e0;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
            font-weight: 500;
        }}
        nav a:hover, nav a.active {{
            background: linear-gradient(90deg, #e94560, #ff6b6b);
            color: #fff;
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(233, 69, 96, 0.4);
        }}
        .card {{
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(10px);
            padding: 25px;
            margin: 15px 0;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        }}
        .card h2 {{
            color: #ff6b6b;
            font-size: 20px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(233, 69, 96, 0.3);
        }}
        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
        }}
        .stat {{
            background: rgba(255, 255, 255, 0.05);
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            transition: transform 0.3s ease;
        }}
        .stat:hover {{ transform: translateY(-5px); }}
        .stat-value {{ 
            font-size: 32px; 
            font-weight: bold; 
            color: #4ecca3;
            text-shadow: 0 0 20px rgba(78, 204, 163, 0.3);
        }}
        .stat-label {{ color: #a0a0a0; font-size: 14px; margin-top: 8px; }}
        .warning {{
            background: linear-gradient(90deg, rgba(255, 193, 7, 0.2), rgba(255, 152, 0, 0.2));
            border-left: 4px solid #ffc107;
            padding: 15px 20px;
            border-radius: 8px;
            margin: 15px 0;
            color: #ffd54f;
        }}
        .config-item {{
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .config-item:last-child {{ border-bottom: none; }}
        .config-label {{ color: #a0a0a0; }}
        .config-value {{ color: #4ecca3; font-weight: 600; }}
        .group-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 15px;
        }}
        .group-tag {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
        }}
        .empty-text {{ color: #666; font-style: italic; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 边狱巴士攻略管理系统</h1>
        </div>
        
        {_render_nav(self.token, 'status')}
        
        <div class="warning">
            &#9888;&#65039; <strong>安全提示</strong>：请勿泄露URL中的Token，建议使用Nginx反向代理并启用HTTPS加密。
        </div>
        
        <div class="card">
            <h2>&#128421;&#65039; 运行状态</h2>
            <div class="stat-grid">
                <div class="stat">
                    <div class="stat-value">&#9989;</div>
                    <div class="stat-label">服务状态：运行中</div>
                </div>
                <div class="stat">
                    <div class="stat-value" style="font-size: 18px;">{self.host}:{self.port}</div>
                    <div class="stat-label">监听地址</div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>&#128200; 知识库统计</h2>
            <div class="stat-grid">
                <div class="stat">
                    <div class="stat-value">{stats['global']['doc_count']}</div>
                    <div class="stat-label">全局文档数</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{stats['global']['chunk_count']}</div>
                    <div class="stat-label">全局分块数</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{len(group_ids)}</div>
                    <div class="stat-label">群组数量</div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>&#9881;&#65039; 配置信息</h2>
            <div class="config-item">
                <span class="config-label">检索返回数量 (TopK)</span>
                <span class="config-value">{self.config.get('top_k', 6)}</span>
            </div>
            <div class="config-item">
                <span class="config-label">分块大小</span>
                <span class="config-value">{self.config.get('chunk_size', 800)} 字符</span>
            </div>
            <div class="config-item">
                <span class="config-label">分块重叠</span>
                <span class="config-value">{self.config.get('overlap', 120)} 字符</span>
            </div>
            <div class="config-item">
                <span class="config-label">群覆盖加权</span>
                <span class="config-value">{self.config.get('group_boost', 1.2)}x</span>
            </div>
        </div>
        
        <div class="card">
            <h2>&#128101; 群组列表</h2>
            {_render_group_tags(group_ids)}
        </div>
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
<html lang="zh-CN">
<head>
    <title>文档管理 - 边狱巴士攻略</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(90deg, #e94560 0%, #ff6b6b 100%);
            padding: 30px;
            border-radius: 16px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(233, 69, 96, 0.3);
        }}
        .header h1 {{ color: #fff; font-size: 28px; font-weight: 700; }}
        nav {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        nav a {{
            color: #e0e0e0;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
            font-weight: 500;
        }}
        nav a:hover, nav a.active {{
            background: linear-gradient(90deg, #e94560, #ff6b6b);
            color: #fff;
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(233, 69, 96, 0.4);
        }}
        .card {{
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(10px);
            padding: 25px;
            margin: 15px 0;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        }}
        .card h2 {{
            color: #ff6b6b;
            font-size: 20px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(233, 69, 96, 0.3);
        }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid rgba(255, 255, 255, 0.1); }}
        th {{ 
            background: rgba(233, 69, 96, 0.2); 
            color: #ff6b6b;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 12px;
            letter-spacing: 1px;
        }}
        tr:hover {{ background: rgba(255, 255, 255, 0.05); }}
        .btn {{
            padding: 10px 20px;
            cursor: pointer;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
            font-size: 14px;
        }}
        .btn-danger {{
            background: linear-gradient(90deg, #dc3545, #c82333);
            color: white;
        }}
        .btn-danger:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.4);
        }}
        .btn-primary {{
            background: linear-gradient(90deg, #4ecca3, #38b984);
            color: white;
        }}
        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(78, 204, 163, 0.4);
        }}
        .form-group {{
            margin-bottom: 20px;
        }}
        .form-group label {{
            display: block;
            margin-bottom: 8px;
            color: #a0a0a0;
            font-weight: 500;
        }}
        input[type="file"], input[type="text"], select {{
            width: 100%;
            padding: 12px 16px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            color: #e0e0e0;
            font-size: 14px;
            transition: border-color 0.3s ease;
        }}
        input:focus, select:focus {{
            outline: none;
            border-color: #4ecca3;
        }}
        select option {{ background: #1a1a2e; color: #e0e0e0; }}
        .empty-row {{ color: #666; font-style: italic; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>&#128196; 文档管理</h1>
        </div>
        
        {_render_nav(self.token, 'docs')}
        
        <div class="card">
            <h2>&#128228; 上传文档</h2>
            <form id="uploadForm" enctype="multipart/form-data">
                <div class="form-group">
                    <label>选择文件（支持 .txt, .md）</label>
                    <input type="file" name="file" accept=".txt,.md" required>
                </div>
                <div class="form-group">
                    <label>存储范围</label>
                    <select name="scope" id="scopeSelect">
                        <option value="global">&#127760; 全局知识库</option>
                        <option value="group">&#128101; 群覆盖库</option>
                    </select>
                </div>
                <div class="form-group" id="groupIdDiv" style="display:none;">
                    <label>群号</label>
                    <input type="text" name="group_id" placeholder="请输入群号">
                </div>
                <button type="submit" class="btn btn-primary">&#128228; 上传文档</button>
            </form>
        </div>
        
        <div class="card">
            <h2>&#127760; 全局知识库 ({len(global_docs)} 篇文档)</h2>
            <table>
                <tr><th>ID</th><th>文档名称</th><th>字符数</th><th>创建时间</th><th>操作</th></tr>
                {_render_global_doc_rows(global_docs)}
            </table>
            <div style="margin-top: 20px;">
                <button class="btn btn-danger" onclick="clearGlobal()">&#9888;&#65039; 清空全局库</button>
            </div>
        </div>
        
        <div class="card">
            <h2>&#128101; 群覆盖库 ({len(group_docs)} 篇文档)</h2>
            <table>
                <tr><th>ID</th><th>文档名称</th><th>群号</th><th>字符数</th><th>创建时间</th><th>操作</th></tr>
                {_render_group_doc_rows(group_docs)}
            </table>
        </div>
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
                    alert('&#9989; 上传成功！');
                    location.reload();
                }} else {{
                    alert('&#10060; 上传失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('&#10060; 上传失败：' + err.message);
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
                    alert('&#10060; 删除失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('&#10060; 删除失败：' + err.message);
            }}
        }}
        
        async function clearGlobal() {{
            if (!confirm('&#9888;&#65039; 确定要清空整个全局库吗？此操作不可恢复！')) return;
            if (!confirm('&#9888;&#65039; 再次确认：真的要清空全局库吗？')) return;
            try {{
                const resp = await fetch('/docs/clear?scope=global&token=' + token, {{
                    method: 'DELETE'
                }});
                if (resp.ok) {{
                    location.reload();
                }} else {{
                    const data = await resp.json();
                    alert('&#10060; 清空失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('&#10060; 清空失败：' + err.message);
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
<html lang="zh-CN">
<head>
    <title>分块浏览 - 边狱巴士攻略</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(90deg, #e94560 0%, #ff6b6b 100%);
            padding: 30px;
            border-radius: 16px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(233, 69, 96, 0.3);
        }}
        .header h1 {{ color: #fff; font-size: 28px; font-weight: 700; }}
        nav {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        nav a {{
            color: #e0e0e0;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
            font-weight: 500;
        }}
        nav a:hover, nav a.active {{
            background: linear-gradient(90deg, #e94560, #ff6b6b);
            color: #fff;
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(233, 69, 96, 0.4);
        }}
        .card {{
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(10px);
            padding: 25px;
            margin: 15px 0;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        }}
        .card h2 {{
            color: #ff6b6b;
            font-size: 20px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(233, 69, 96, 0.3);
        }}
        .chunk {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            margin: 15px 0;
            padding: 20px;
            border-radius: 12px;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        .chunk:hover {{
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.3);
        }}
        .chunk-header {{
            font-weight: 600;
            color: #4ecca3;
            margin-bottom: 10px;
            font-size: 14px;
        }}
        .chunk-tags {{ margin: 10px 0; }}
        .tag {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 4px 12px;
            margin: 3px;
            border-radius: 15px;
            font-size: 12px;
            color: #fff;
        }}
        .chunk-content {{
            white-space: pre-wrap;
            font-size: 14px;
            max-height: 200px;
            overflow-y: auto;
            padding: 15px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 8px;
            color: #c0c0c0;
            line-height: 1.8;
        }}
        .form-row {{
            display: flex;
            gap: 15px;
            align-items: center;
            flex-wrap: wrap;
        }}
        input[type="text"], input[type="number"] {{
            padding: 12px 16px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            color: #e0e0e0;
            font-size: 14px;
            transition: border-color 0.3s ease;
        }}
        input:focus {{ outline: none; border-color: #4ecca3; }}
        .btn {{
            padding: 12px 24px;
            cursor: pointer;
            border: none;
            border-radius: 8px;
            background: linear-gradient(90deg, #4ecca3, #38b984);
            color: white;
            font-weight: 600;
            transition: all 0.3s ease;
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(78, 204, 163, 0.4);
        }}
        .empty-text {{ color: #666; font-style: italic; text-align: center; padding: 40px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>&#128230; 分块浏览</h1>
        </div>
        
        {_render_nav(self.token, 'chunks')}
        
        <div class="card">
            <h2>🔎 筛选条件</h2>
            <form method="get">
                <input type="hidden" name="token" value="{self.token}">
                <div class="form-row">
                    <input type="text" name="group_id" placeholder="输入群号筛选" value="{group_id or ''}">
                    <input type="number" name="doc_id" placeholder="输入文档ID筛选" value="{doc_id or ''}">
                    <button type="submit" class="btn">&#128269; 筛选</button>
                </div>
            </form>
        </div>
        
        <div class="card">
            <h2>&#128203; 分块列表（显示前100条，共 {len(chunks)} 条）</h2>
            {_render_chunks(chunks)}
        </div>
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
<html lang="zh-CN">
<head>
    <title>检索调试 - 边狱巴士攻略</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(90deg, #e94560 0%, #ff6b6b 100%);
            padding: 30px;
            border-radius: 16px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(233, 69, 96, 0.3);
        }}
        .header h1 {{ color: #fff; font-size: 28px; font-weight: 700; }}
        nav {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        nav a {{
            color: #e0e0e0;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
            font-weight: 500;
        }}
        nav a:hover, nav a.active {{
            background: linear-gradient(90deg, #e94560, #ff6b6b);
            color: #fff;
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(233, 69, 96, 0.4);
        }}
        .card {{
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(10px);
            padding: 25px;
            margin: 15px 0;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        }}
        .card h2 {{
            color: #ff6b6b;
            font-size: 20px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(233, 69, 96, 0.3);
        }}
        .form-group {{ margin-bottom: 15px; }}
        .form-group label {{ display: block; margin-bottom: 8px; color: #a0a0a0; font-weight: 500; }}
        input[type="text"], input[type="number"] {{
            width: 100%;
            max-width: 400px;
            padding: 12px 16px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            color: #e0e0e0;
            font-size: 14px;
            transition: border-color 0.3s ease;
        }}
        input:focus {{ outline: none; border-color: #4ecca3; }}
        .inline-group {{ display: flex; gap: 15px; align-items: center; }}
        .inline-group input {{ width: 100px; }}
        .btn {{
            padding: 12px 24px;
            cursor: pointer;
            border: none;
            border-radius: 8px;
            background: linear-gradient(90deg, #4ecca3, #38b984);
            color: white;
            font-weight: 600;
            transition: all 0.3s ease;
            font-size: 14px;
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(78, 204, 163, 0.4);
        }}
        .result {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            margin: 15px 0;
            padding: 20px;
            border-radius: 12px;
            transition: transform 0.3s ease;
        }}
        .result:hover {{ transform: translateY(-3px); }}
        .result-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .result-info {{ color: #a0a0a0; font-size: 14px; }}
        .score {{
            background: linear-gradient(90deg, #4ecca3, #38b984);
            padding: 6px 12px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 14px;
        }}
        .breakdown {{
            color: #666;
            font-size: 12px;
            margin: 10px 0;
            padding: 10px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 6px;
        }}
        .content {{
            white-space: pre-wrap;
            font-size: 14px;
            margin-top: 15px;
            padding: 15px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 8px;
            max-height: 150px;
            overflow-y: auto;
            color: #c0c0c0;
        }}
        .tag {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 4px 12px;
            margin: 3px;
            border-radius: 15px;
            font-size: 12px;
            color: #fff;
        }}
        .tag.matched {{
            background: linear-gradient(90deg, #4ecca3, #38b984);
        }}
        .query-info {{
            background: rgba(78, 204, 163, 0.1);
            border-left: 4px solid #4ecca3;
            padding: 15px 20px;
            border-radius: 8px;
            margin: 15px 0;
        }}
        .query-info strong {{ color: #4ecca3; }}
        #results {{ display: none; }}
        .empty-text {{ color: #666; font-style: italic; text-align: center; padding: 40px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>&#128269; 检索调试</h1>
        </div>
        
        {_render_nav(self.token, 'search')}
        
        <div class="card">
            <h2>🔎 搜索测试</h2>
            <form id="searchForm">
                <div class="form-group">
                    <label>查询问题</label>
                    <input type="text" id="query" placeholder="输入要检索的问题..." required>
                </div>
                <div class="form-group">
                    <label>群号（可选）</label>
                    <input type="text" id="groupId" placeholder="留空则搜索全局">
                </div>
                <div class="form-group">
                    <div class="inline-group">
                        <label style="margin-bottom:0;">返回数量</label>
                        <input type="number" id="topK" value="6" min="1" max="20">
                    </div>
                </div>
                <button type="submit" class="btn">&#128269; 开始检索</button>
            </form>
        </div>
        
        <div id="results" class="card">
            <h2>&#128202; 检索结果</h2>
            <div id="queryInfo" class="query-info"></div>
            <div id="resultsList"></div>
        </div>
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
                    <strong>&#128203; 查询分析</strong><br><br>
                    <b>原始查询：</b>${{info.original_query || query}}<br>
                    <b>处理后：</b>${{info.processed_query || query}}<br>
                    <b>提取标签：</b>${{(info.extracted_tags || []).join(', ') || '无'}}<br>
                    <b>别名替换：</b>${{(info.alias_substitutions || []).join(', ') || '无'}}
                `;
                
                // Results
                const results = data.results || [];
                if (results.length === 0) {{
                    document.getElementById('resultsList').innerHTML = '<p class="empty-text">未找到匹配结果</p>';
                }} else {{
                    document.getElementById('resultsList').innerHTML = results.map((r, i) => `
                        <div class="result">
                            <div class="result-header">
                                #${{i+1}} | Chunk ${{r.id}} | 
                                ${{r.scope}} ${{r.group_id ? ['(', r.group_id, ')'].join('') : ''}}
                                <span class="score">得分: ${{r.score.toFixed(3)}}</span>
                            </div>
                            <div class="breakdown">
                                &#128202; BM25: ${{r.score_breakdown?.bm25?.toFixed(3) || 0}} |
                                &#127991;&#65039; 标签加权: ${{r.score_breakdown?.tag_boost?.toFixed(3) || 0}} |
                                &#128101; 群加权: ${{r.score_breakdown?.group_boost?.toFixed(3) || 0}}
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
                alert('&#10060; 搜索失败：' + err.message);
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
            
            # Type display mapping
            type_display = {
                'identity': '&#128100; 人格',
                'ego': '&#127917; EGO',
                'status': '&#9889; 状态',
                'mode': '&#127918; 模式',
                'other': '&#128203; 其他'
            }
            
            html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <title>别名词典 - 边狱巴士攻略</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(90deg, #e94560 0%, #ff6b6b 100%);
            padding: 30px;
            border-radius: 16px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(233, 69, 96, 0.3);
        }}
        .header h1 {{ color: #fff; font-size: 28px; font-weight: 700; }}
        nav {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        nav a {{
            color: #e0e0e0;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
            font-weight: 500;
        }}
        nav a:hover, nav a.active {{
            background: linear-gradient(90deg, #e94560, #ff6b6b);
            color: #fff;
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(233, 69, 96, 0.4);
        }}
        .card {{
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(10px);
            padding: 25px;
            margin: 15px 0;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        }}
        .card h2 {{
            color: #ff6b6b;
            font-size: 20px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(233, 69, 96, 0.3);
        }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid rgba(255, 255, 255, 0.1); }}
        th {{ 
            background: rgba(233, 69, 96, 0.2); 
            color: #ff6b6b;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 12px;
            letter-spacing: 1px;
        }}
        tr:hover {{ background: rgba(255, 255, 255, 0.05); }}
        .btn {{
            padding: 10px 20px;
            cursor: pointer;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
            font-size: 14px;
        }}
        .btn-danger {{
            background: linear-gradient(90deg, #dc3545, #c82333);
            color: white;
        }}
        .btn-danger:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.4);
        }}
        .btn-primary {{
            background: linear-gradient(90deg, #4ecca3, #38b984);
            color: white;
        }}
        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(78, 204, 163, 0.4);
        }}
        .form-group {{ margin-bottom: 20px; }}
        .form-group label {{
            display: block;
            margin-bottom: 8px;
            color: #a0a0a0;
            font-weight: 500;
        }}
        input[type="text"], select {{
            width: 100%;
            max-width: 400px;
            padding: 12px 16px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            color: #e0e0e0;
            font-size: 14px;
            transition: border-color 0.3s ease;
        }}
        input:focus, select:focus {{ outline: none; border-color: #4ecca3; }}
        select option {{ background: #1a1a2e; color: #e0e0e0; }}
        .empty-row {{ color: #666; font-style: italic; text-align: center; }}
        .type-badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }}
        .type-identity {{ background: linear-gradient(135deg, #667eea, #764ba2); }}
        .type-ego {{ background: linear-gradient(135deg, #f093fb, #f5576c); }}
        .type-status {{ background: linear-gradient(135deg, #4facfe, #00f2fe); }}
        .type-mode {{ background: linear-gradient(135deg, #43e97b, #38f9d7); }}
        .type-other {{ background: linear-gradient(135deg, #fa709a, #fee140); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>&#128221; 别名词典</h1>
        </div>
        
        {_render_nav(self.token, 'aliases')}
        
        <div class="card">
            <h2>&#10133; 添加别名</h2>
            <form id="aliasForm">
                <div class="form-group">
                    <label>别名（玩家常用称呼）</label>
                    <input type="text" id="alias" placeholder="例如：红叔、老福、以实玛利" required>
                </div>
                <div class="form-group">
                    <label>标准名（官方正式名称）</label>
                    <input type="text" id="canonical" placeholder="例如：洪鹿、浮士德、以实玛利" required>
                </div>
                <div class="form-group">
                    <label>类型</label>
                    <select id="aliasType">
                        <option value="identity">&#128100; 人格</option>
                        <option value="ego">&#127917; EGO</option>
                        <option value="status">&#9889; 状态</option>
                        <option value="mode">&#127918; 模式</option>
                        <option value="other" selected>&#128203; 其他</option>
                    </select>
                </div>
                <button type="submit" class="btn btn-primary">&#10133; 添加别名</button>
            </form>
        </div>
        
        <div class="card">
            <h2>&#128203; 别名列表（共 {len(aliases)} 条）</h2>
            <table>
                <tr><th>别名</th><th>标准名</th><th>类型</th><th>创建时间</th><th>操作</th></tr>
                {_render_alias_rows(aliases, type_display)}
            </table>
        </div>
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
                    alert('&#9989; 添加成功！');
                    location.reload();
                }} else {{
                    const data = await resp.json();
                    alert('&#10060; 添加失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('&#10060; 添加失败：' + err.message);
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
                    alert('&#10060; 删除失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('&#10060; 删除失败：' + err.message);
            }}
        }}
    </script>
</body>
</html>
"""
            return HTMLResponse(content=html)
        
        @app.get("/model-settings-page", response_class=HTMLResponse)
        async def model_settings_page(request: Request, _=Depends(verify_token)):
            """Model settings page with embedding and reranking status"""
            embedding_status = self.config.get('embedding_status', {
                'enabled': False, 'implemented': False, 'provider_id': None, 'message': '状态未知'
            })
            reranking_status = self.config.get('reranking_status', {
                'enabled': False, 'implemented': False, 'provider_id': None, 'message': '状态未知'
            })
            
            # Determine status display
            def get_status_display(status):
                if status.get('implemented'):
                    return ('&#9989;', '已实现', 'status-implemented')
                elif status.get('enabled'):
                    return ('&#9888;&#65039;', '已启用但未实现', 'status-enabled')
                else:
                    return ('&#10060;', '未启用', 'status-disabled')
            
            emb_icon, emb_text, emb_class = get_status_display(embedding_status)
            rer_icon, rer_text, rer_class = get_status_display(reranking_status)
            
            html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <title>模型设置 - 边狱巴士攻略</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(90deg, #e94560 0%, #ff6b6b 100%);
            padding: 30px;
            border-radius: 16px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(233, 69, 96, 0.3);
        }}
        .header h1 {{ color: #fff; font-size: 28px; font-weight: 700; }}
        nav {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        nav a {{
            color: #e0e0e0;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
            font-weight: 500;
        }}
        nav a:hover, nav a.active {{
            background: linear-gradient(90deg, #e94560, #ff6b6b);
            color: #fff;
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(233, 69, 96, 0.4);
        }}
        .card {{
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(10px);
            padding: 25px;
            margin: 15px 0;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        }}
        .card h2 {{
            color: #ff6b6b;
            font-size: 20px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(233, 69, 96, 0.3);
        }}
        .model-card {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 25px;
            margin: 15px 0;
            border-radius: 12px;
        }}
        .model-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        .model-title {{
            font-size: 18px;
            font-weight: 600;
            color: #4ecca3;
        }}
        .model-status {{
            padding: 6px 16px;
            border-radius: 20px;
            font-weight: 500;
            font-size: 14px;
        }}
        .status-implemented {{ background: rgba(78, 204, 163, 0.2); color: #4ecca3; }}
        .status-enabled {{ background: rgba(255, 193, 7, 0.2); color: #ffc107; }}
        .status-disabled {{ background: rgba(108, 117, 125, 0.2); color: #6c757d; }}
        .model-info {{
            margin-top: 15px;
        }}
        .info-item {{
            display: flex;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}
        .info-item:last-child {{ border-bottom: none; }}
        .info-label {{ width: 120px; color: #a0a0a0; }}
        .info-value {{ color: #e0e0e0; }}
        .info-help {{
            margin-top: 15px;
            padding: 15px;
            background: rgba(78, 204, 163, 0.1);
            border-left: 4px solid #4ecca3;
            border-radius: 8px;
            font-size: 14px;
            color: #a0a0a0;
        }}
        .info-help strong {{ color: #4ecca3; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>&#9881;&#65039; 模型设置</h1>
        </div>
        
        {_render_nav(self.token, 'model')}
        
        <div class="card">
            <h2>&#128301; 检索增强模型状态</h2>
            <p style="color: #a0a0a0; margin-bottom: 20px;">
                检索增强功能可以提高知识库检索的精确度和相关性。这些模型需要在AstrBot主程序中配置后才能使用。
            </p>
            
            <div class="model-card">
                <div class="model-header">
                    <span class="model-title">&#128203; 引用嵌入 (Embedding)</span>
                    <span class="model-status {emb_class}">{emb_icon} {emb_text}</span>
                </div>
                <p style="color: #a0a0a0; font-size: 14px;">
                    嵌入模型将文本转换为向量，实现语义级别的相似度搜索。启用后可以理解同义词和上下文，而不仅仅是关键词匹配。
                </p>
                <div class="model-info">
                    <div class="info-item">
                        <span class="info-label">启用状态</span>
                        <span class="info-value">{'是' if embedding_status.get('enabled') else '否'}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">实现状态</span>
                        <span class="info-value">{'是' if embedding_status.get('implemented') else '否'}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">提供者ID</span>
                        <span class="info-value">{embedding_status.get('provider_id') or '未配置'}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">状态信息</span>
                        <span class="info-value">{embedding_status.get('message') or '-'}</span>
                    </div>
                </div>
                <div class="info-help">
                    <strong>&#128161; 如何启用：</strong><br>
                    1. 在AstrBot管理面板中配置嵌入模型提供者（如OpenAI Embedding、Cohere等）<br>
                    2. 在插件配置中设置 <code>use_embedding = true</code><br>
                    3. 重启插件以使配置生效
                </div>
            </div>
            
            <div class="model-card">
                <div class="model-header">
                    <span class="model-title">&#128300; 重排序 (Reranking)</span>
                    <span class="model-status {rer_class}">{rer_icon} {rer_text}</span>
                </div>
                <p style="color: #a0a0a0; font-size: 14px;">
                    重排序模型对初步检索结果进行精细排序，提高最终结果的相关性。通常与嵌入模型配合使用效果最佳。
                </p>
                <div class="model-info">
                    <div class="info-item">
                        <span class="info-label">启用状态</span>
                        <span class="info-value">{'是' if reranking_status.get('enabled') else '否'}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">实现状态</span>
                        <span class="info-value">{'是' if reranking_status.get('implemented') else '否'}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">提供者ID</span>
                        <span class="info-value">{reranking_status.get('provider_id') or '未配置'}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">状态信息</span>
                        <span class="info-value">{reranking_status.get('message') or '-'}</span>
                    </div>
                </div>
                <div class="info-help">
                    <strong>&#128161; 如何启用：</strong><br>
                    1. 在AstrBot管理面板中配置重排序模型提供者（如Cohere Rerank等）<br>
                    2. 在插件配置中设置 <code>use_reranking = true</code><br>
                    3. 重启插件以使配置生效
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>&#9881;&#65039; 当前检索配置</h2>
            <div class="model-info">
                <div class="info-item">
                    <span class="info-label">TopK</span>
                    <span class="info-value">{self.config.get('top_k', 6)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">分块大小</span>
                    <span class="info-value">{self.config.get('chunk_size', 800)} 字符</span>
                </div>
                <div class="info-item">
                    <span class="info-label">分块重叠</span>
                    <span class="info-value">{self.config.get('overlap', 120)} 字符</span>
                </div>
                <div class="info-item">
                    <span class="info-label">群覆盖加权</span>
                    <span class="info-value">{self.config.get('group_boost', 1.2)}x</span>
                </div>
            </div>
            <div class="info-help">
                <strong>&#128161; 提示：</strong>这些配置需要在AstrBot管理面板的插件配置中修改，修改后重启插件生效。
            </div>
        </div>
    </div>
</body>
</html>
"""
            return HTMLResponse(content=html)
        
        @app.get("/template-page", response_class=HTMLResponse)
        async def template_page(request: Request, _=Depends(verify_token)):
            """Document template management page"""
            templates = await self.db.get_templates()
            
            # Import the default template from prompts module
            from ..core.prompts import DOCUMENT_TEMPLATE
            
            html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <title>文档模版 - 边狱巴士攻略</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(90deg, #e94560 0%, #ff6b6b 100%);
            padding: 30px;
            border-radius: 16px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(233, 69, 96, 0.3);
        }}
        .header h1 {{ color: #fff; font-size: 28px; font-weight: 700; }}
        nav {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        nav a {{
            color: #e0e0e0;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
            font-weight: 500;
        }}
        nav a:hover, nav a.active {{
            background: linear-gradient(90deg, #e94560, #ff6b6b);
            color: #fff;
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(233, 69, 96, 0.4);
        }}
        .card {{
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(10px);
            padding: 25px;
            margin: 15px 0;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        }}
        .card h2 {{
            color: #ff6b6b;
            font-size: 20px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(233, 69, 96, 0.3);
        }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid rgba(255, 255, 255, 0.1); }}
        th {{ 
            background: rgba(233, 69, 96, 0.2); 
            color: #ff6b6b;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 12px;
            letter-spacing: 1px;
        }}
        tr:hover {{ background: rgba(255, 255, 255, 0.05); }}
        .btn {{
            padding: 8px 16px;
            cursor: pointer;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
            font-size: 13px;
            margin: 2px;
        }}
        .btn-sm {{ padding: 6px 12px; font-size: 12px; }}
        .btn-danger {{
            background: linear-gradient(90deg, #dc3545, #c82333);
            color: white;
        }}
        .btn-primary {{
            background: linear-gradient(90deg, #4ecca3, #38b984);
            color: white;
        }}
        .btn-secondary {{
            background: rgba(255, 255, 255, 0.1);
            color: #e0e0e0;
        }}
        .btn:hover {{ transform: translateY(-2px); }}
        .form-group {{ margin-bottom: 20px; }}
        .form-group label {{
            display: block;
            margin-bottom: 8px;
            color: #a0a0a0;
            font-weight: 500;
        }}
        input[type="text"], textarea {{
            width: 100%;
            padding: 12px 16px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            color: #e0e0e0;
            font-size: 14px;
            transition: border-color 0.3s ease;
        }}
        input:focus, textarea:focus {{ outline: none; border-color: #4ecca3; }}
        textarea {{
            min-height: 400px;
            font-family: 'Consolas', 'Monaco', monospace;
            line-height: 1.6;
            resize: vertical;
        }}
        .empty-row {{ color: #666; font-style: italic; text-align: center; }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 500;
        }}
        .badge-default {{ background: rgba(78, 204, 163, 0.2); color: #4ecca3; }}
        .template-content {{
            background: rgba(0, 0, 0, 0.3);
            padding: 20px;
            border-radius: 8px;
            max-height: 500px;
            overflow-y: auto;
            white-space: pre-wrap;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 13px;
            line-height: 1.6;
            color: #c0c0c0;
        }}
        .tab-buttons {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }}
        .tab-btn {{
            padding: 10px 20px;
            background: rgba(255, 255, 255, 0.1);
            border: none;
            border-radius: 8px;
            color: #e0e0e0;
            cursor: pointer;
            transition: all 0.3s ease;
        }}
        .tab-btn.active {{
            background: linear-gradient(90deg, #4ecca3, #38b984);
            color: white;
        }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        #templateEditor {{ display: none; }}
        #templateEditor.active {{ display: block; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>&#128203; 文档模版（中文版）</h1>
        </div>
        
        {_render_nav(self.token, 'template')}
        
        <div class="card">
            <h2>&#128196; 默认中文模板</h2>
            <p style="color: #a0a0a0; margin-bottom: 15px;">
                这是系统内置的默认中文攻略文档模板，可以直接复制使用，或基于此创建自定义模板。
            </p>
            <div class="template-content">{DOCUMENT_TEMPLATE}</div>
            <div style="margin-top: 15px;">
                <button class="btn btn-primary" onclick="copyDefaultTemplate()">&#128203; 复制模板</button>
                <button class="btn btn-secondary" onclick="showCreateForm()">&#10133; 基于此创建自定义模板</button>
            </div>
        </div>
        
        <div class="card" id="templateEditor">
            <h2 id="editorTitle">&#10133; 创建自定义模板</h2>
            <form id="templateForm">
                <div class="form-group">
                    <label>模板名称</label>
                    <input type="text" id="templateName" placeholder="例如：燃烧队专用模板" required>
                </div>
                <div class="form-group">
                    <label>模板描述（可选）</label>
                    <input type="text" id="templateDesc" placeholder="简短描述模板的用途">
                </div>
                <div class="form-group">
                    <label>模板内容</label>
                    <textarea id="templateContent" placeholder="在此输入模板内容..."></textarea>
                </div>
                <button type="submit" class="btn btn-primary">&#128190; 保存模板</button>
                <button type="button" class="btn btn-secondary" onclick="hideEditor()">取消</button>
            </form>
        </div>
        
        <div class="card">
            <h2>&#128203; 自定义模板列表（共 {len(templates)} 个）</h2>
            <table>
                <tr><th>名称</th><th>描述</th><th>大小</th><th>更新时间</th><th>操作</th></tr>
                {_render_template_rows(templates)}
            </table>
        </div>
    </div>
    
    <script>
        const token = '{self.token}';
        const defaultTemplate = {json.dumps(DOCUMENT_TEMPLATE)};
        let editingTemplate = null;
        
        function copyDefaultTemplate() {{
            navigator.clipboard.writeText(defaultTemplate).then(() => {{
                alert('&#9989; 模板已复制到剪贴板！');
            }}).catch(err => {{
                alert('&#10060; 复制失败，请手动选择复制');
            }});
        }}
        
        function showCreateForm() {{
            document.getElementById('templateEditor').classList.add('active');
            document.getElementById('editorTitle').textContent = '&#10133; 创建自定义模板';
            document.getElementById('templateName').value = '';
            document.getElementById('templateDesc').value = '';
            document.getElementById('templateContent').value = defaultTemplate;
            editingTemplate = null;
        }}
        
        function hideEditor() {{
            document.getElementById('templateEditor').classList.remove('active');
            editingTemplate = null;
        }}
        
        async function editTemplate(name) {{
            try {{
                const resp = await fetch('/templates/' + encodeURIComponent(name) + '?token=' + encodeURIComponent(token));
                if (!resp.ok) {{
                    const data = await resp.json();
                    alert('&#10060; 加载模板失败：' + (data.detail || '未知错误'));
                    return;
                }}
                const data = await resp.json();
                if (data.template) {{
                    document.getElementById('templateEditor').classList.add('active');
                    document.getElementById('editorTitle').textContent = '&#9998; 编辑模板';
                    document.getElementById('templateName').value = data.template.name;
                    document.getElementById('templateDesc').value = data.template.description || '';
                    document.getElementById('templateContent').value = data.template.content;
                    editingTemplate = name;
                }} else {{
                    alert('&#10060; 模板数据为空');
                }}
            }} catch (err) {{
                alert('&#10060; 加载模板失败：' + err.message);
            }}
        }}
        
        document.getElementById('templateForm').onsubmit = async function(e) {{
            e.preventDefault();
            const name = document.getElementById('templateName').value;
            const description = document.getElementById('templateDesc').value;
            const content = document.getElementById('templateContent').value;
            
            try {{
                const resp = await fetch('/templates?token=' + encodeURIComponent(token), {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{name, content, description}})
                }});
                if (resp.ok) {{
                    alert('&#9989; 模板保存成功！');
                    location.reload();
                }} else {{
                    const data = await resp.json();
                    alert('&#10060; 保存失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('&#10060; 保存失败：' + err.message);
            }}
        }};
        
        async function deleteTemplate(name) {{
            if (!confirm('确定要删除模板 "' + name + '" 吗？')) return;
            try {{
                const resp = await fetch('/templates/' + encodeURIComponent(name) + '?token=' + encodeURIComponent(token), {{
                    method: 'DELETE'
                }});
                if (resp.ok) {{
                    location.reload();
                }} else {{
                    const data = await resp.json();
                    alert('&#10060; 删除失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('&#10060; 删除失败：' + err.message);
            }}
        }}
    </script>
</body>
</html>
"""
            return HTMLResponse(content=html)
        
        @app.get("/status-mapping-page", response_class=HTMLResponse)
        async def status_mapping_page(request: Request, _=Depends(verify_token)):
            """Status subcategory mapping management page"""
            mappings = await self.db.get_status_mappings()
            
            # Default status categories
            status_options = [
                ('burn', '燃烧 (Burn)'),
                ('bleed', '流血 (Bleed)'),
                ('tremor', '震颤 (Tremor)'),
                ('rupture', '破裂 (Rupture)'),
                ('sinking', '沉沦 (Sinking)'),
                ('poise', '蓄力 (Poise)'),
                ('charge', '充能 (Charge)'),
                ('other', '其他'),
            ]
            
            status_options_html = ''.join(
                f'<option value="{val}">{label}</option>' 
                for val, label in status_options
            )
            
            html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <title>状态映射 - 边狱巴士攻略</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(90deg, #e94560 0%, #ff6b6b 100%);
            padding: 30px;
            border-radius: 16px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(233, 69, 96, 0.3);
        }}
        .header h1 {{ color: #fff; font-size: 28px; font-weight: 700; }}
        nav {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        nav a {{
            color: #e0e0e0;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
            font-weight: 500;
        }}
        nav a:hover, nav a.active {{
            background: linear-gradient(90deg, #e94560, #ff6b6b);
            color: #fff;
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(233, 69, 96, 0.4);
        }}
        .card {{
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(10px);
            padding: 25px;
            margin: 15px 0;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        }}
        .card h2 {{
            color: #ff6b6b;
            font-size: 20px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(233, 69, 96, 0.3);
        }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid rgba(255, 255, 255, 0.1); }}
        th {{ 
            background: rgba(233, 69, 96, 0.2); 
            color: #ff6b6b;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 12px;
            letter-spacing: 1px;
        }}
        tr:hover {{ background: rgba(255, 255, 255, 0.05); }}
        .btn {{
            padding: 10px 20px;
            cursor: pointer;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
            font-size: 14px;
        }}
        .btn-danger {{
            background: linear-gradient(90deg, #dc3545, #c82333);
            color: white;
        }}
        .btn-primary {{
            background: linear-gradient(90deg, #4ecca3, #38b984);
            color: white;
        }}
        .btn:hover {{ transform: translateY(-2px); }}
        .form-group {{ margin-bottom: 20px; }}
        .form-group label {{
            display: block;
            margin-bottom: 8px;
            color: #a0a0a0;
            font-weight: 500;
        }}
        input[type="text"], select {{
            width: 100%;
            max-width: 400px;
            padding: 12px 16px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            color: #e0e0e0;
            font-size: 14px;
            transition: border-color 0.3s ease;
        }}
        input:focus, select:focus {{ outline: none; border-color: #4ecca3; }}
        select option {{ background: #1a1a2e; color: #e0e0e0; }}
        .empty-row {{ color: #666; font-style: italic; text-align: center; }}
        .info-box {{
            background: rgba(78, 204, 163, 0.1);
            border-left: 4px solid #4ecca3;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 14px;
            color: #a0a0a0;
        }}
        .info-box strong {{ color: #4ecca3; }}
        .example-box {{
            background: rgba(255, 193, 7, 0.1);
            border-left: 4px solid #ffc107;
            padding: 15px 20px;
            border-radius: 8px;
            margin: 15px 0;
            font-size: 14px;
            color: #a0a0a0;
        }}
        .example-box strong {{ color: #ffc107; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>&#127991;&#65039; 状态/子类映射</h1>
        </div>
        
        {_render_nav(self.token, 'mapping')}
        
        <div class="card">
            <h2>&#9881;&#65039; 功能说明</h2>
            <div class="info-box">
                <strong>&#128161; 什么是状态映射？</strong><br>
                状态映射允许你为游戏中的状态效果定义自定义子类别和显示名称。
                这在检索时可以帮助更精确地匹配用户的查询意图。
            </div>
            <div class="example-box">
                <strong>&#128221; 使用示例：</strong><br>
                • 状态：<strong>破裂 (rupture)</strong> → 子类别：<strong>被动破裂</strong> → 显示名称：<strong>非破裂但有破裂效果</strong><br>
                • 状态：<strong>燃烧 (burn)</strong> → 子类别：<strong>燃烧叠层</strong> → 显示名称：<strong>高叠层燃烧流派</strong><br>
                • 状态：<strong>震颤 (tremor)</strong> → 子类别：<strong>震颤爆发</strong> → 显示名称：<strong>震颤计数触发伤害</strong>
            </div>
        </div>
        
        <div class="card">
            <h2>&#10133; 添加状态映射</h2>
            <form id="mappingForm">
                <div class="form-group">
                    <label>主状态类别</label>
                    <select id="statusName" required>
                        {status_options_html}
                    </select>
                </div>
                <div class="form-group">
                    <label>子类别名称</label>
                    <input type="text" id="subcategory" placeholder="例如：被动破裂、高叠层燃烧" required>
                </div>
                <div class="form-group">
                    <label>显示名称</label>
                    <input type="text" id="displayName" placeholder="例如：非破裂但有破裂效果" required>
                </div>
                <div class="form-group">
                    <label>描述（可选）</label>
                    <input type="text" id="mappingDesc" placeholder="简短描述这个子类别的特点">
                </div>
                <button type="submit" class="btn btn-primary">&#10133; 添加映射</button>
            </form>
        </div>
        
        <div class="card">
            <h2>&#128203; 映射列表（共 {len(mappings)} 条）</h2>
            <table>
                <tr><th>主状态</th><th>子类别</th><th>显示名称</th><th>描述</th><th>操作</th></tr>
                {_render_status_mapping_rows(mappings)}
            </table>
        </div>
    </div>
    
    <script>
        const token = '{self.token}';
        
        document.getElementById('mappingForm').onsubmit = async function(e) {{
            e.preventDefault();
            const status_name = document.getElementById('statusName').value;
            const subcategory = document.getElementById('subcategory').value;
            const display_name = document.getElementById('displayName').value;
            const description = document.getElementById('mappingDesc').value;
            
            try {{
                const resp = await fetch('/status-mappings?token=' + token, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{status_name, subcategory, display_name, description}})
                }});
                if (resp.ok) {{
                    alert('&#9989; 映射添加成功！');
                    location.reload();
                }} else {{
                    const data = await resp.json();
                    alert('&#10060; 添加失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('&#10060; 添加失败：' + err.message);
            }}
        }};
        
        async function deleteMapping(id) {{
            if (!confirm('确定要删除这个映射吗？')) return;
            try {{
                const resp = await fetch('/status-mappings/' + id + '?token=' + token, {{
                    method: 'DELETE'
                }});
                if (resp.ok) {{
                    location.reload();
                }} else {{
                    const data = await resp.json();
                    alert('&#10060; 删除失败：' + (data.detail || '未知错误'));
                }}
            }} catch (err) {{
                alert('&#10060; 删除失败：' + err.message);
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
        
        # ============ Template API ============
        
        @app.get("/templates")
        async def list_templates(_=Depends(verify_token)):
            """List all custom templates"""
            templates = await self.db.get_templates()
            return {"templates": templates}
        
        @app.get("/templates/{name}")
        async def get_template(name: str, _=Depends(verify_token)):
            """Get a template by name"""
            template = await self.db.get_template_by_name(name)
            if not template:
                raise HTTPException(status_code=404, detail="模板不存在")
            return {"template": template}
        
        class TemplateRequest(BaseModel):
            name: str
            content: str
            description: str = ''
            is_default: bool = False
        
        @app.post("/templates")
        async def save_template(request: TemplateRequest, _=Depends(verify_token)):
            """Save or update a custom template"""
            template_id = await self.db.save_template(
                name=request.name,
                content=request.content,
                description=request.description,
                is_default=request.is_default
            )
            return {"success": True, "id": template_id}
        
        @app.delete("/templates/{name}")
        async def delete_template(name: str, _=Depends(verify_token)):
            """Delete a custom template"""
            success = await self.db.delete_template(name)
            if not success:
                raise HTTPException(status_code=404, detail="模板不存在")
            return {"success": True}
        
        # ============ Status Mapping API ============
        
        @app.get("/status-mappings")
        async def list_status_mappings(status_name: Optional[str] = None, _=Depends(verify_token)):
            """List status mappings"""
            mappings = await self.db.get_status_mappings(status_name)
            return {"mappings": mappings}
        
        class StatusMappingRequest(BaseModel):
            status_name: str
            subcategory: str
            display_name: str
            description: str = ''
        
        @app.post("/status-mappings")
        async def add_status_mapping(request: StatusMappingRequest, _=Depends(verify_token)):
            """Add or update a status mapping"""
            mapping_id = await self.db.add_status_mapping(
                status_name=request.status_name,
                subcategory=request.subcategory,
                display_name=request.display_name,
                description=request.description
            )
            return {"success": True, "id": mapping_id}
        
        @app.delete("/status-mappings/{mapping_id}")
        async def delete_status_mapping(mapping_id: int, _=Depends(verify_token)):
            """Delete a status mapping"""
            success = await self.db.delete_status_mapping(mapping_id)
            if not success:
                raise HTTPException(status_code=404, detail="映射不存在")
            return {"success": True}
        
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
