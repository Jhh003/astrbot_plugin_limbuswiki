"""
Limbus Company Guide Plugin for AstrBot
A RAG-based game guide query plugin for Limbus Company
"""
import os
import asyncio
from datetime import datetime
from typing import Optional, Dict, Set

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.api import logger, AstrBotConfig

from .core.database import Database
from .core.chunker import Chunker
from .core.tagger import Tagger
from .core.searcher import Searcher
from .core.prompts import (
    PromptBuilder, 
    DOCUMENT_TEMPLATE, 
    HELP_TEXT, 
    STATUS_TEMPLATE,
    IMPORT_START_TEXT,
    IMPORT_SUCCESS_TEMPLATE
)


@register(
    "astrbot_plugin_limbuswiki",
    "Jhh003",
    "Limbus Company（边狱巴士）游戏攻略查询插件，支持RAG检索和WebUI管理",
    "1.0.0",
    "https://github.com/Jhh003/astrbot_plugin_limbuswiki"
)
class LimbusGuidePlugin(Star):
    """Limbus Company game guide query plugin with RAG support"""
    
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        
        # Get plugin data directory
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_limbuswiki")
        self.db_path = os.path.join(self.data_dir, "limbus_guide.db")
        
        # Configuration with defaults
        self.top_k = config.get("top_k", 6)
        self.chunk_size = config.get("chunk_size", 800)
        self.overlap = config.get("overlap", 120)
        self.group_boost = config.get("group_boost", 1.2)
        
        # Embedding and reranking configuration
        self.use_embedding = config.get("use_embedding", False)
        self.use_reranking = config.get("use_reranking", False)
        
        # WebUI configuration
        self.webui_enabled = config.get("webui_enabled", True)
        self.webui_host = config.get("webui_host", "0.0.0.0")
        self.webui_port = config.get("webui_port", 8765)
        self.webui_token = config.get("webui_token", "")
        
        # Initialize components (will be set in initialize())
        self.db: Optional[Database] = None
        self.chunker: Optional[Chunker] = None
        self.tagger: Optional[Tagger] = None
        self.searcher: Optional[Searcher] = None
        self.webui = None
        
        # Import session management: {unified_msg_origin: session_data}
        self.import_sessions: Dict[str, dict] = {}
        
    async def initialize(self):
        """Initialize plugin components"""
        logger.info("Initializing Limbus Guide Plugin...")
        
        # Initialize database
        self.db = Database(self.db_path)
        await self.db.init()
        
        # Initialize processing components
        self.chunker = Chunker(chunk_size=self.chunk_size, overlap=self.overlap)
        self.tagger = Tagger()
        self.searcher = Searcher()
        
        # Configure embedding and reranking providers if enabled
        await self._configure_search_providers()
        
        # Load existing data into searcher
        await self._rebuild_search_index()
        
        # Load aliases
        alias_map = await self.db.get_alias_map()
        self.searcher.update_aliases(alias_map)
        
        # Start WebUI server
        if self.webui_enabled:
            await self._start_webui()
        
        logger.info("Limbus Guide Plugin initialized successfully")
    
    async def _configure_search_providers(self):
        """Configure embedding and reranking providers from AstrBot"""
        # Configure embedding provider
        if self.use_embedding:
            try:
                embedding_providers = self.context.get_all_embedding_providers()
                if embedding_providers:
                    self.searcher.set_embedding_provider(embedding_providers[0])
                    logger.info(f"Embedding provider configured: {embedding_providers[0].meta().id}")
                else:
                    logger.warning("Embedding enabled but no embedding provider available in AstrBot")
            except Exception as e:
                logger.warning(f"Failed to configure embedding provider: {e}")
        
        # Configure reranking provider
        if self.use_reranking:
            try:
                # Try to get reranking provider from context
                rerank_provider = None
                # Check if context has get_all_rerank_providers method (newer AstrBot versions)
                if hasattr(self.context, 'provider_manager'):
                    pm = self.context.provider_manager
                    if hasattr(pm, 'rerank_provider_insts'):
                        rerank_providers = pm.rerank_provider_insts
                        if rerank_providers:
                            rerank_provider = rerank_providers[0]
                
                if rerank_provider:
                    self.searcher.set_rerank_provider(rerank_provider)
                    logger.info(f"Reranking provider configured: {rerank_provider.meta().id}")
                else:
                    logger.warning("Reranking enabled but no reranking provider available in AstrBot")
            except Exception as e:
                logger.warning(f"Failed to configure reranking provider: {e}")
    
    async def _rebuild_search_index(self, group_id: Optional[str] = None):
        """Rebuild search index from database"""
        chunks = await self.db.get_all_chunks_for_search(group_id)
        self.searcher.update_chunks(chunks)
        logger.info(f"Search index rebuilt with {len(chunks)} chunks")
    
    async def _start_webui(self):
        """Start the WebUI server"""
        try:
            from .webui.server import WebUIServer
            
            webui_config = {
                'webui_enabled': self.webui_enabled,
                'webui_host': self.webui_host,
                'webui_port': self.webui_port,
                'webui_token': self.webui_token,
                'top_k': self.top_k,
                'chunk_size': self.chunk_size,
                'overlap': self.overlap,
                'group_boost': self.group_boost,
            }
            
            self.webui = WebUIServer(
                db=self.db,
                chunker=self.chunker,
                tagger=self.tagger,
                searcher=self.searcher,
                config=webui_config,
                on_index_update=self._rebuild_search_index
            )
            
            await self.webui.start()
            
            # Store generated token if not configured
            if not self.webui_token:
                self.webui_token = self.webui.get_token()
            
            logger.info(f"WebUI started at http://{self.webui_host}:{self.webui_port}")
            logger.info(f"WebUI Token: {self.webui_token}")
            
        except ImportError as e:
            logger.warning(f"WebUI dependencies not available: {e}")
            logger.warning("WebUI is disabled. Install fastapi and uvicorn to enable.")
            logger.info("插件核心功能（问答、导入等）仍可正常使用。")
            self.webui = None
        except RuntimeError as e:
            # RuntimeError is raised by WebUIServer for startup failures
            logger.error(f"WebUI启动失败: {e}")
            logger.error("请检查端口配置或依赖安装情况。")
            logger.info("插件核心功能（问答、导入等）仍可正常使用。")
            self.webui = None
        except Exception as e:
            logger.error(f"WebUI启动时发生意外错误: {e}")
            logger.info("插件核心功能（问答、导入等）仍可正常使用。")
            self.webui = None
    
    # ============ Command Handlers ============
    
    @filter.command("guide")
    async def guide_command(self, event: AstrMessageEvent):
        """主指令路由"""
        message = event.message_str.strip()
        parts = message.split(maxsplit=2)
        
        if len(parts) < 2:
            # Just "/guide" - show help
            yield event.plain_result(HELP_TEXT)
            return
        
        subcommand = parts[1].lower()
        args = parts[2] if len(parts) > 2 else ""
        
        if subcommand == "help":
            yield event.plain_result(HELP_TEXT)
        elif subcommand == "template":
            yield event.plain_result(DOCUMENT_TEMPLATE)
        elif subcommand == "status":
            async for result in self._handle_status(event):
                yield result
        elif subcommand == "import":
            async for result in self._handle_import_start(event):
                yield result
        elif subcommand == "clear":
            async for result in self._handle_clear(event):
                yield result
        elif subcommand == "mode":
            async for result in self._handle_mode(event, args):
                yield result
        else:
            yield event.plain_result(f"未知子命令: {subcommand}\n使用 /guide help 查看帮助")
    
    async def _handle_status(self, event: AstrMessageEvent):
        """Handle /guide status command"""
        group_id = event.get_group_id() or "private"
        is_admin = event.is_admin()
        
        # Get stats
        stats = await self.db.get_stats(group_id)
        settings = await self.db.get_group_settings(group_id)
        
        # Format last import time
        last_import = settings.get('last_import_at')
        if last_import:
            last_import = last_import[:19]
        else:
            last_import = "从未导入"
        
        # Search enhancement info
        search_enhancement = ""
        if self.use_embedding or self.use_reranking:
            enhancements = []
            if self.use_embedding:
                enhancements.append("嵌入模型")
            if self.use_reranking:
                enhancements.append("重排序模型")
            search_enhancement = f"\n【检索增强】\n已启用：{', '.join(enhancements)}"
        
        # WebUI info (only for admins)
        webui_info = ""
        if is_admin and self.webui_enabled and self.webui:
            webui_info = f"""
【WebUI管理】
地址：{self.webui.get_url()}
Token：{self.webui_token}
⚠️ 请勿泄露Token！"""
        elif is_admin:
            webui_info = "\n【WebUI】未启用"
        
        status_text = STATUS_TEMPLATE.format(
            group_id=group_id,
            default_mode=settings.get('default_mode', 'simple'),
            last_import=last_import,
            global_docs=stats['global']['doc_count'],
            global_chunks=stats['global']['chunk_count'],
            group_docs=stats['group']['doc_count'],
            group_chunks=stats['group']['chunk_count'],
            top_k=self.top_k,
            chunk_size=self.chunk_size,
            overlap=self.overlap,
            search_enhancement=search_enhancement,
            webui_info=webui_info
        )
        
        yield event.plain_result(status_text)
    
    async def _handle_import_start(self, event: AstrMessageEvent):
        """Handle /guide import command - start import session"""
        # Check admin permission
        if not event.is_admin():
            yield event.plain_result("❌ 仅管理员可以导入攻略文档")
            return
        
        umo = event.unified_msg_origin
        group_id = event.get_group_id() or "private"
        
        # Create import session
        self.import_sessions[umo] = {
            'group_id': group_id,
            'texts': [],
            'started_at': datetime.now(),
            'timeout': 60
        }
        
        yield event.plain_result(IMPORT_START_TEXT)
    
    async def _handle_clear(self, event: AstrMessageEvent):
        """Handle /guide clear command"""
        if not event.is_admin():
            yield event.plain_result("❌ 仅管理员可以清空知识库")
            return
        
        group_id = event.get_group_id() or "private"
        
        # Clear group-specific documents only
        await self.db.clear_documents(scope='group', group_id=group_id)
        await self._rebuild_search_index()
        
        yield event.plain_result(f"✅ 已清空群 {group_id} 的覆盖知识库")
    
    async def _handle_mode(self, event: AstrMessageEvent, args: str):
        """Handle /guide mode command"""
        group_id = event.get_group_id() or "private"
        
        if not args:
            # Show current mode
            settings = await self.db.get_group_settings(group_id)
            current_mode = settings.get('default_mode', 'simple')
            yield event.plain_result(f"当前默认回答模式：{current_mode}")
            return
        
        mode = args.lower().strip()
        if mode not in ('simple', 'detail'):
            yield event.plain_result("❌ 模式只能是 simple 或 detail")
            return
        
        await self.db.update_group_settings(group_id, default_mode=mode)
        yield event.plain_result(f"✅ 已将默认回答模式设置为：{mode}")
    
    # ============ Import Session Handlers ============
    
    @filter.command("done")
    async def handle_done(self, event: AstrMessageEvent):
        """Handle /done command to finish import"""
        umo = event.unified_msg_origin
        
        if umo not in self.import_sessions:
            yield event.plain_result("当前没有进行中的导入会话")
            return
        
        session = self.import_sessions[umo]
        texts = session['texts']
        group_id = session['group_id']
        
        if not texts:
            del self.import_sessions[umo]
            yield event.plain_result("❌ 没有收到任何文本内容，导入已取消")
            return
        
        # Combine all texts
        full_text = "\n\n".join(texts)
        doc_name = f"guide_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Process document
        try:
            doc_id = await self.db.add_document(
                name=doc_name,
                raw_text=full_text,
                scope='group',
                group_id=group_id
            )
            
            # Chunk and tag
            chunks = self.chunker.process_document(full_text, doc_name)
            chunks = self.tagger.process_chunks(chunks)
            
            # Save chunks
            await self.db.add_chunks(
                doc_id=doc_id,
                chunks=chunks,
                scope='group',
                group_id=group_id
            )
            
            # Update group settings
            await self.db.update_group_settings(
                group_id, 
                last_import_at=datetime.now().isoformat()
            )
            
            # Rebuild search index
            await self._rebuild_search_index()
            
            # Get tag statistics
            tag_stats = self.tagger.get_tag_statistics(chunks)
            top_tags = list(tag_stats.items())[:5]
            tags_summary = "\n".join(f"- {tag}: {count}次" for tag, count in top_tags)
            if not tags_summary:
                tags_summary = "- 无标签"
            
            result_text = IMPORT_SUCCESS_TEMPLATE.format(
                doc_name=doc_name,
                char_count=len(full_text),
                chunk_count=len(chunks),
                tags_summary=tags_summary
            )
            
            yield event.plain_result(result_text)
            
        except Exception as e:
            logger.error(f"Import failed: {e}")
            yield event.plain_result(f"❌ 导入失败：{str(e)}")
        
        finally:
            del self.import_sessions[umo]
    
    @filter.command("cancel")
    async def handle_cancel(self, event: AstrMessageEvent):
        """Handle /cancel command to cancel import"""
        umo = event.unified_msg_origin
        
        if umo in self.import_sessions:
            del self.import_sessions[umo]
            yield event.plain_result("✅ 导入已取消")
        else:
            yield event.plain_result("当前没有进行中的导入会话")
    
    # ============ Message Handlers ============
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """Handle all messages for import sessions and @bot queries"""
        umo = event.unified_msg_origin
        message = event.message_str.strip()
        
        # Check for active import session
        if umo in self.import_sessions:
            # Skip if it's a command
            if message.startswith('/'):
                return
            
            # Check timeout
            session = self.import_sessions[umo]
            elapsed = (datetime.now() - session['started_at']).total_seconds()
            if elapsed > session['timeout']:
                del self.import_sessions[umo]
                yield event.plain_result("⏰ 导入会话已超时，请重新开始")
                return
            
            # Add text to session
            session['texts'].append(message)
            # Don't respond to every message, just collect
            return
        
        # Check for @bot mention (for Q&A)
        if event.is_at_or_wake_command:
            # Skip if it's a /guide command
            if message.startswith('/guide') or message.startswith('guide'):
                return
            
            # Handle Q&A
            async for result in self._handle_qa(event, message):
                yield result
    
    async def _handle_qa(self, event: AstrMessageEvent, query: str):
        """Handle Q&A queries"""
        group_id = event.get_group_id() or "private"
        
        # Check if knowledge base is empty - let other handlers process if no knowledge base
        stats = await self.db.get_stats(group_id)
        if stats['total']['chunk_count'] == 0:
            # Knowledge base is empty, skip processing to allow other AI features
            return
        
        # Clean query
        query = query.strip()
        if not query:
            return
        
        # Get group settings
        settings = await self.db.get_group_settings(group_id)
        default_mode = settings.get('default_mode', 'simple')
        
        # Detect mode from query
        mode = PromptBuilder.detect_mode_from_query(query, default_mode)
        
        # Search for relevant chunks using async search (supports embedding & reranking if configured)
        if self.use_embedding or self.use_reranking:
            results = await self.searcher.search_async(query, top_k=self.top_k, group_id=group_id)
        else:
            results = self.searcher.search(query, top_k=self.top_k, group_id=group_id)
        
        if not results:
            # No relevant content found, skip processing to allow other AI features
            return
        
        # Build prompts
        system_prompt = PromptBuilder.build_system_prompt(mode)
        context_prompt = PromptBuilder.build_context_prompt(results, query)
        
        # Call LLM
        try:
            llm_request = event.request_llm(
                prompt=context_prompt,
                system_prompt=system_prompt
            )
            
            # Get LLM response
            provider = self.context.get_using_provider()
            if provider:
                response = await provider.text_chat(**llm_request.__dict__)
                if response and response.completion_text:
                    yield event.plain_result(response.completion_text)
                else:
                    yield event.plain_result("❌ LLM响应为空，请稍后重试")
            else:
                yield event.plain_result("❌ 没有可用的LLM提供者，请检查配置")
                
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            yield event.plain_result(f"❌ 查询失败：{str(e)}")
    
    # ============ LLM Tool ============
    
    @filter.llm_tool(name="query_limbus_guide")
    async def llm_tool_query(
        self,
        event: AstrMessageEvent,
        question: str
    ) -> str:
        """
        查询Limbus Company（边狱巴士）游戏攻略
        Args:
            question(str): 用户关于Limbus Company游戏的问题
        """
        group_id = event.get_group_id() or "private"
        
        # Search for relevant chunks using async search if embedding/reranking is enabled
        if self.use_embedding or self.use_reranking:
            results = await self.searcher.search_async(question, top_k=self.top_k, group_id=group_id)
        else:
            results = self.searcher.search(question, top_k=self.top_k, group_id=group_id)
        
        if not results:
            return "知识库中没有找到相关信息，请建议用户补充相关攻略文档。"
        
        # Build context for LLM tool response (more natural format)
        context_parts = []
        for i, chunk in enumerate(results[:3]):  # Top 3 for tool
            content = chunk['content'][:300]
            if len(chunk['content']) > 300:
                content += "..."
            context_parts.append(f"参考资料{i+1}：{content}")
        
        return "找到以下相关信息：\n\n" + "\n\n".join(context_parts)
    
    async def terminate(self):
        """Cleanup when plugin is unloaded"""
        logger.info("Shutting down Limbus Guide Plugin...")
        
        # Stop WebUI
        if self.webui:
            await self.webui.stop()
        
        # Close database
        if self.db:
            await self.db.close()
        
        logger.info("Limbus Guide Plugin shutdown complete")
