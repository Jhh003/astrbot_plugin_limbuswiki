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

1. **只能使用参考资料中的信息作答**。如果参考资料中没有相关信息，你必须明确告知用户"资料不足以确定"。

2. **禁止编造**：
   - 不要编造任何数值（伤害、概率、系数等）
   - 不要编造游戏机制的细节
   - 不要编造版本改动信息
   - 不要编造人格/EGO的技能效果

3. **如果资料不足**：
   - 明确说明哪些信息是确定的，哪些是不确定的
   - 列出需要用户补充的信息
   - 可以基于游戏通用逻辑给出方向性建议，但要注明这是推测

4. **引用来源**：在回答中标注信息来源的chunk编号，格式如 [chunk:X]

## 游戏术语提示：
- 罪孽(Sin)：暴食、色欲、懒惰、暴怒、忧郁、傲慢、嫉妒
- 状态效果：燃烧(Burn)、流血(Bleed)、震颤(Tremor)、破裂(Rupture)、沉沦(Sinking)、蓄力(Poise)
- 伤害类型：斩击(Slash)、穿刺(Pierce)、钝击(Blunt)
"""

    SIMPLE_FORMAT = """
## 回答格式（简单版）：

1. **一句话结论**：直接回答用户的核心问题

2. **步骤/要点**（3-6条）：
   - 简明扼要的操作步骤或关键点
   - 每条不超过两行

3. **注意事项**（1-3条）：
   - 常见错误或需要留意的地方

4. **资料不足说明**（如有）：
   - 列出无法确定的信息
   - 建议用户补充的内容
"""

    DETAILED_FORMAT = """
## 回答格式（详细版）：

1. **概览**：问题的完整回答概述

2. **机制/条件**（如适用）：
   - 相关游戏机制的详细解释
   - 触发条件、计算方式等

3. **详细步骤**：
   - 分阶段的操作指南
   - 每个阶段的具体操作和注意事项

4. **替代方案/低配方案**（如有）：
   - 可替换的人格/EGO
   - 适合不同资源程度的玩家的方案

5. **常见问题/坑**：
   - 容易犯的错误
   - FAQ形式的补充说明

6. **引用来源**：
   - 列出使用到的chunk编号
   - 格式：[chunk:X], [chunk:Y], ...

7. **资料不足说明**（如有）：
   - 无法确定的信息列表
   - 建议补充的内容
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
            chunk_id = chunk.get('id', i)
            content = chunk.get('content', '')
            tags = chunk.get('tags', [])
            scope = chunk.get('scope', 'unknown')
            
            tags_str = f"[标签: {', '.join(tags)}]" if tags else ""
            scope_str = f"[来源: {'全局库' if scope == 'global' else '群覆盖库'}]"
            
            context_parts.append(f"""--- Chunk {chunk_id} {scope_str} {tags_str} ---
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
3. 标注引用的chunk编号"""
    
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

## 文档信息
- 游戏：Limbus Company（边狱巴士）
- 文档名：[填写文档名称]
- 版本/更新时间：[填写版本号或日期]
- 适用模式：主线 / 镜牢 / 铁道 / 活动（删除不适用的）

---

## 【术语与机制】

### 拼点/硬币机制
[在这里介绍拼点、硬币、速度等核心机制]
- 拼点规则：
- 硬币计算：
- 速度影响：

### 罪孽资源
[介绍七种罪孽资源和共鸣机制]
- 共鸣触发条件：
- 完全共鸣效果：

### 状态效果
[介绍各种状态效果]
- 燃烧(Burn)：
- 流血(Bleed)：
- 震颤(Tremor)：
- 破裂(Rupture)：
- 沉沦(Sinking)：
- 蓄力(Poise)：

---

## 【人格指南】

### [人格名称1]
**定位**：输出/坦克/辅助/控场
**核心机制**：
**技能要点**：
- 技能1：
- 技能2：
- 技能3：
**适用场景**：
**替代方案**：

### [人格名称2]
...

---

## 【EGO 指南】

### [EGO名称1]
**所属角色**：
**资源消耗**：
**用途**：
**使用时机**：
**注意事项**：（侵蚀/副作用等）

### [EGO名称2]
...

---

## 【配队/构筑】

### [体系名称] 配队
**核心机制**：（如 Burn体系、Rupture体系等）
**核心成员**：
1. 
2. 
3. 

**替补选择**：
- 

**打法思路**：
1. 
2. 
3. 

---

## 【关卡/模式攻略】

### [模式/关卡名称]
**推荐配队**：
**步骤**：
1. 
2. 
3. 

**常见坑**：
- 

---

## 【FAQ】

**Q: [常见问题1]**
A: 

**Q: [常见问题2]**
A: 

---

## 标签提示

为了帮助机器人更好地检索，请在文档中适当使用以下关键词：
- 机制类：拼点、硬币、速度、罪孽、共鸣、结算
- 人格类：人格、ID、000、00、0（稀有度标记）
- EGO类：EGO、侵蚀、腐蚀
- 模式类：镜牢、MD、铁道、RR、活动、主线、Boss
- 状态类：燃烧/Burn、流血/Bleed、震颤/Tremor、破裂/Rupture、沉沦/Sinking、蓄力/Poise

---

*文档结束*
"""


HELP_TEXT = """📖 **Limbus Company 攻略查询插件**

**基本用法**：
- 在群里 @机器人 + 问题，即可获得基于攻略库的回答
- 例如：@机器人 燃烧队怎么配？

**管理员指令**：
- `/guide import` - 导入攻略文档（进入导入模式）
- `/guide clear` - 清空本群的覆盖知识库

**通用指令**：
- `/guide help` - 显示此帮助信息
- `/guide template` - 获取攻略文档模板
- `/guide status` - 查看知识库状态
- `/guide mode simple|detail` - 设置默认回答模式

**回答模式**：
- 简单版（默认）：精简的步骤和要点
- 详细版：完整的机制解释和多方案

**触发详细回答**：
在问题中包含以下关键词会自动使用详细模式：
详细、展开、机制、原理、配装、怎么配、长一点

**知识库说明**：
- 全局库：所有群共享的攻略内容（通过WebUI上传）
- 群覆盖库：仅本群可用的攻略内容（通过 /guide import 导入）
- 检索时会同时搜索两个库，群覆盖库的内容有更高优先级

**WebUI管理**：
管理员可通过 /guide status 查看WebUI访问地址和Token
"""


STATUS_TEMPLATE = """📊 **知识库状态**

**本群信息**：
- 群号：{group_id}
- 默认模式：{default_mode}
- 最后导入：{last_import}

**知识库统计**：
- 全局文档：{global_docs} 篇
- 全局Chunks：{global_chunks} 条
- 群覆盖文档：{group_docs} 篇
- 群覆盖Chunks：{group_chunks} 条

**检索配置**：
- TopK：{top_k}
- Chunk大小：{chunk_size} 字符
- 重叠：{overlap} 字符

{webui_info}
"""


IMPORT_START_TEXT = """📥 **导入模式已开启**

请在 **60秒内** 完成以下操作：

1. 发送攻略文本（可分多条消息）
2. 或上传 txt/md 文件

完成后发送 `/done` 结束导入

**提示**：
- 建议先用 `/guide template` 获取模板
- 使用模板格式的文档检索效果更好
- 导入内容将保存到本群的覆盖知识库

发送 `/cancel` 可取消导入
"""


IMPORT_SUCCESS_TEMPLATE = """✅ **导入成功！**

**文档信息**：
- 文档名：{doc_name}
- 字符数：{char_count}
- Chunk数：{chunk_count}

**主要标签**：
{tags_summary}

现在可以 @机器人 提问了！
"""
