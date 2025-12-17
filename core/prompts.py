"""
Prompt builder for Limbus Guide Plugin
Builds prompts for LLM with anti-hallucination constraints
"""
from typing import List, Dict


class PromptBuilder:
    """Builds prompts for LLM responses with retrieval context"""
    
    SYSTEM_PROMPT_TEMPLATE = """你是一个专业的《Limbus Company》（边狱巴士）游戏攻略助手。
你的任务是基于提供的参考资料回答用户关于游戏的问题。

## 重要规则（必须严格遵守）：

1. 只能使用参考资料中的信息作答。如果参考资料中没有相关信息，你必须明确告知用户"资料不足以确定"。

2. 禁止编造：
   - 不要编造任何数值（伤害、概率、系数等）
   - 不要编造游戏机制的细节
   - 不要编造版本改动信息
   - 不要编造人格/EGO的技能效果

3. 如果资料不足：
   - 明确说明哪些信息是确定的，哪些是不确定的
   - 列出需要用户补充的信息
   - 可以基于游戏通用逻辑给出方向性建议，但要注明这是推测

4. 回答格式要求：
   - 用自然流畅的语言回答，像一个真人玩家在回答问题
   - 不要使用Markdown格式符号（如*、**、#等）
   - 不要在回答中标注任何参考来源或编号
   - 用清晰的段落和换行来组织内容，而不是列表符号

## 游戏术语提示：
- 罪孽(Sin)：暴食、色欲、懒惰、暴怒、忧郁、傲慢、嫉妒
- 状态效果：燃烧(Burn)、流血(Bleed)、震颤(Tremor)、破裂(Rupture)、沉沦(Sinking)、蓄力(Poise)
- 伤害类型：斩击(Slash)、穿刺(Pierce)、钝击(Blunt)
"""

    SIMPLE_FORMAT = """
## 回答风格（简洁版）：

用简洁自然的语言回答，包含以下内容：

1. 直接回答用户的核心问题（一两句话）

2. 列出3-6个关键要点或操作步骤

3. 如有需要，提醒1-3个注意事项

4. 如果资料不足，说明哪些信息无法确定

注意：回答要像朋友聊天一样自然，不要用Markdown格式，不要标注参考来源。
"""

    DETAILED_FORMAT = """
## 回答风格（详细版）：

用详细但自然的语言回答，包含以下内容：

1. 先给出问题的概览性回答

2. 详细解释相关的游戏机制和触发条件

3. 分步骤说明具体的操作方法

4. 如果有替代方案或低配方案，也一并说明

5. 提醒一些常见的坑或容易犯的错误

6. 如果资料不足，说明哪些信息无法确定

注意：回答要像一个资深玩家在耐心讲解，语言要自然流畅，不要用Markdown格式，不要标注参考来源。
"""

    @classmethod
    def build_system_prompt(cls, mode: str = 'simple') -> str:
        """Build system prompt with format instructions"""
        base = cls.SYSTEM_PROMPT_TEMPLATE
        
        if mode == 'detail':
            return base + cls.DETAILED_FORMAT
        else:
            return base + cls.SIMPLE_FORMAT
    
    @classmethod
    def build_context_prompt(cls, chunks: List[Dict], query: str) -> str:
        """Build the user prompt with context and query"""
        if not chunks:
            return f"""用户问题：{query}

注意：当前没有找到相关的参考资料。请告知用户需要先导入攻略文档。"""
        
        # Build context section
        context_parts = []
        for i, chunk in enumerate(chunks):
            content = chunk.get('content', '')
            tags = chunk.get('tags', [])
            scope = chunk.get('scope', 'unknown')
            
            tags_str = f"[标签: {', '.join(tags)}]" if tags else ""
            scope_str = f"[来源: {'全局库' if scope == 'global' else '群覆盖库'}]"
            
            context_parts.append(f"""--- 参考资料{i+1} {scope_str} {tags_str} ---
{content}
""")
        
        context_text = "\n".join(context_parts)
        
        return f"""## 参考资料

{context_text}

---

## 用户问题

{query}

请基于以上参考资料回答用户的问题。记住：
1. 只使用参考资料中的信息
2. 不确定的内容要明确说明
3. 用自然流畅的语言回答，不要使用Markdown格式符号"""
    
    @classmethod
    def detect_mode_from_query(cls, query: str, default_mode: str = 'simple') -> str:
        """
        Detect response mode from query keywords
        
        Returns 'detail' if query contains detail-triggering keywords,
        otherwise returns default_mode
        """
        detail_keywords = [
            '详细', '展开', '详细说', '详细讲',
            '机制', '原理', '为什么',
            '配装', '怎么配', '怎么搭',
            '长一点', '详细点', '具体',
            '深入', '解释', '说明'
        ]
        
        query_lower = query.lower()
        for keyword in detail_keywords:
            if keyword in query_lower:
                return 'detail'
        
        return default_mode


# Document template for users
DOCUMENT_TEMPLATE = """# Limbus Company 攻略文档模板

这是一个灵活的攻略文档框架，你可以根据需要选择使用的模块，也可以自由添加新的分类。

================================================================================
基础信息（建议保留）
================================================================================

文档名称：[填写文档名称，如"燃烧队配队指南"]
更新日期：[填写日期]
适用内容：[简述本文档涵盖的内容范围]

================================================================================
正文内容（以下模块可选，按需使用或自行添加）
================================================================================

【主题/标题】

在这里写你的攻略内容。你可以自由组织格式，比如：

关于xxx的说明：
这里写具体内容...

要点总结：
1. 第一点
2. 第二点
3. 第三点

注意事项：
- 注意点1
- 注意点2

--------------------------------------------------------------------------------

【另一个主题】

继续写其他内容...

================================================================================
可选模块参考（复制需要的部分使用）
================================================================================

--- 人格介绍模块 ---
【人格名称】
角色：xxx
稀有度：000/00/0
定位：输出/辅助/坦克
核心机制：xxx
技能说明：xxx
适用场景：xxx
搭配建议：xxx

--- EGO介绍模块 ---
【EGO名称】
所属角色：xxx
消耗资源：xxx
效果说明：xxx
使用时机：xxx
注意事项：xxx

--- 配队模块 ---
【配队名称】（如：燃烧队/破裂队/沉沦队等）
核心思路：xxx
核心成员：xxx
替补选择：xxx
打法说明：xxx

--- 关卡攻略模块 ---
【关卡/Boss名称】
推荐配置：xxx
攻略步骤：xxx
注意事项：xxx
常见问题：xxx

--- 机制说明模块 ---
【机制名称】
基本原理：xxx
触发条件：xxx
伤害计算：xxx（如适用）
相关技能/人格：xxx

--- FAQ模块 ---
【常见问题】
Q：问题1？
A：回答1

Q：问题2？
A：回答2

================================================================================
关键词提示（帮助检索，可在文中自然使用）
================================================================================

以下关键词可以帮助机器人更好地检索你的文档内容：

游戏模式：主线、镜牢、MD、铁道、RR、活动
状态效果：燃烧、流血、震颤、破裂、沉沦、蓄力、Burn、Bleed、Tremor、Rupture、Sinking、Poise
游戏机制：拼点、硬币、速度、罪孽、共鸣、EGO、侵蚀
角色相关：人格、ID、000、00、配队、阵容

================================================================================
文档结束
================================================================================
"""


HELP_TEXT = """📖 Limbus Company 攻略查询插件

【基本用法】
在群里 @机器人 + 问题，即可获得基于攻略库的回答
例如：@机器人 燃烧队怎么配？

【管理员指令】
/guide import - 导入攻略文档（进入导入模式）
/guide clear - 清空本群的覆盖知识库

【通用指令】
/guide help - 显示此帮助信息
/guide template - 获取攻略文档模板
/guide status - 查看知识库状态
/guide mode simple|detail - 设置默认回答模式

【回答模式】
简单版（默认）：精简的步骤和要点
详细版：完整的机制解释和多方案

【触发详细回答】
在问题中包含以下关键词会自动使用详细模式：
详细、展开、机制、原理、配装、怎么配、长一点

【知识库说明】
全局库：所有群共享的攻略内容（通过WebUI上传）
群覆盖库：仅本群可用的攻略内容（通过 /guide import 导入）
检索时会同时搜索两个库，群覆盖库的内容有更高优先级

【检索增强】
支持启用嵌入模型(Embedding)和重排序模型(Reranking)提高检索精度
需要在AstrBot中配置相应模型后，在插件配置中启用

【WebUI管理】
管理员可通过 /guide status 查看WebUI访问地址和Token
"""


STATUS_TEMPLATE = """📊 知识库状态

【本群信息】
群号：{group_id}
默认模式：{default_mode}
最后导入：{last_import}

【知识库统计】
全局文档：{global_docs} 篇
全局Chunks：{global_chunks} 条
群覆盖文档：{group_docs} 篇
群覆盖Chunks：{group_chunks} 条

【检索配置】
TopK：{top_k}
Chunk大小：{chunk_size} 字符
重叠：{overlap} 字符
{search_enhancement}
{webui_info}
"""


IMPORT_START_TEXT = """📥 导入模式已开启

请在60秒内完成以下操作：

1. 发送攻略文本（可分多条消息）
2. 或上传 txt/md 文件

完成后发送 /done 结束导入

提示：
- 建议先用 /guide template 获取模板
- 使用模板格式的文档检索效果更好
- 导入内容将保存到本群的覆盖知识库

发送 /cancel 可取消导入
"""


IMPORT_SUCCESS_TEMPLATE = """✅ 导入成功！

【文档信息】
文档名：{doc_name}
字符数：{char_count}
Chunk数：{chunk_count}

【主要标签】
{tags_summary}

现在可以 @机器人 提问了！
"""
