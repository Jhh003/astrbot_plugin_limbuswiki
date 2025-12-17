# Limbus Guide - AstrBot 插件

Limbus Company（边狱巴士）游戏攻略查询插件，支持 RAG 检索增强生成和 WebUI 管理界面。

## ✨ 功能特性

- 📚 **知识库管理**：支持导入、清空攻略文档
- 🔍 **智能检索**：基于 BM25 + 标签加权的检索系统
- 🤖 **AI 问答**：@机器人提问，自动检索相关内容并生成回答
- 🏷️ **自动标签**：根据 Limbus Company 领域关键词自动打标签
- 🌐 **WebUI 管理**：可视化管理知识库、调试检索
- 🔒 **多群隔离**：全局库 + 群覆盖库双层知识库模型
- 🧠 **检索增强**：支持嵌入模型(Embedding)和重排序模型(Reranking)
- 📝 **自定义模板**：支持创建和管理自定义文档模板
- 🏷️ **状态映射**：支持自定义状态子类别映射

## 📦 安装

1. 将此插件放入 AstrBot 的 plugins 目录
2. 安装依赖（可选，用于 WebUI）：
   ```bash
   pip install fastapi uvicorn python-multipart
   ```
3. 重启 AstrBot

## 🚀 快速开始

### 群聊指令

| 指令 | 说明 | 权限 |
|------|------|------|
| `/guide help` | 显示帮助信息 | 所有人 |
| `/guide template` | 获取攻略文档模板 | 所有人 |
| `/guide status` | 查看知识库状态 | 所有人 |
| `/guide import` | 开始导入攻略（60秒内发送内容，/done 结束） | 管理员 |
| `/guide clear` | 清空本群覆盖知识库 | 管理员 |
| `/guide mode simple\|detail` | 设置默认回答模式 | 所有人 |

### @机器人提问

在群里 @机器人 + 问题即可查询：
```
@机器人 燃烧队怎么配？
@机器人 详细讲讲拼点机制
@机器人 镜牢第四层怎么打
```

### 回答模式

- **简单版**（默认）：一句话结论 + 步骤 + 注意事项
- **详细版**：完整机制解释 + 多方案 + 常见坑

在问题中包含以下关键词会自动使用详细模式：
`详细`、`展开`、`机制`、`原理`、`配装`、`怎么配`、`长一点`

## 🧠 检索增强功能

插件支持使用嵌入模型和重排序模型来提升检索精度：

### 引用嵌入 (Embedding)

嵌入模型将文本转换为向量，实现语义级别的相似度搜索。启用后可以理解同义词和上下文，而不仅仅是关键词匹配。

**启用方法**：
1. 在 AstrBot 管理面板中配置嵌入模型提供者（如 OpenAI Embedding、Cohere 等）
2. 在插件配置中设置 `use_embedding = true`
3. 重启插件

### 重排序 (Reranking)

重排序模型对初步检索结果进行精细排序，提高最终结果的相关性。通常与嵌入模型配合使用效果最佳。

**启用方法**：
1. 在 AstrBot 管理面板中配置重排序模型提供者（如 Cohere Rerank 等）
2. 在插件配置中设置 `use_reranking = true`
3. 重启插件

### 状态日志

插件启动时会在日志中显示检索增强功能的实现状态：
```
==================================================
【检索增强功能状态检查】
✅ 引用嵌入(Embedding)功能: 已实现
   - 提供者: openai-embedding
✅ 重排序(Reranking)功能: 已实现
   - 提供者: cohere-rerank
==================================================
```

## 🌐 WebUI 管理

### 访问方式

1. 启动插件后，使用 `/guide status`（管理员）查看 WebUI 地址和 Token
2. 在浏览器访问：`http://<服务器IP>:8765/?token=<your_token>`

### WebUI 功能

- **状态总览**：查看运行状态、知识库统计
- **文档管理**：上传/删除文档，支持全局库和群覆盖库
- **分块浏览**：查看分块内容和标签
- **检索调试**：测试搜索效果，查看得分详情
- **别名词典**：管理关键词别名映射
- **模型设置**：查看嵌入模型和重排序模型的启用状态和实现状态
- **文档模版**：查看默认中文模板，创建和管理自定义模板
- **状态映射**：自定义状态效果的子类别映射

### 文档模版管理

在 WebUI 的「文档模版」页面，您可以：
- 查看并复制默认的中文攻略文档模板
- 基于默认模板创建自定义模板
- 编辑和删除已保存的自定义模板

### 状态映射管理

状态映射允许您为游戏中的状态效果定义自定义子类别和显示名称，便于更精确地匹配用户查询。

**使用示例**：
- 状态：**破裂 (rupture)** → 子类别：**被动破裂** → 显示名称：**非破裂但有破裂效果**
- 状态：**燃烧 (burn)** → 子类别：**燃烧叠层** → 显示名称：**高叠层燃烧流派**
- 状态：**震颤 (tremor)** → 子类别：**震颤爆发** → 显示名称：**震颤计数触发伤害**

### 安全建议

⚠️ **重要安全提示**：

1. **不要泄露 Token**：Token 相当于管理密码
2. **使用 HTTPS**：建议通过 Nginx 反向代理并启用 SSL
3. **限制访问 IP**：在云服务器安全组中限制访问源 IP
4. **定期更换 Token**：在配置中手动设置新的 webui_token

推荐的 Nginx 配置：
```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location /limbus-guide/ {
        proxy_pass http://127.0.0.1:8765/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 📝 攻略文档格式

使用 `/guide template` 获取推荐的文档模板，或在 WebUI 的「文档模版」页面查看和自定义模板。

为了获得最佳检索效果，建议在文档中：

1. 使用清晰的标题结构（`【xxx】` 或 `# xxx`）
2. 包含关键词以便自动打标签：
   - 机制类：拼点、硬币、速度、罪孽、共鸣
   - 人格类：人格、ID、000（三星）、00（二星）
   - EGO 类：EGO、侵蚀、腐蚀
   - 模式类：镜牢、MD、铁道、RR、活动、主线
   - 状态类：燃烧/Burn、流血/Bleed、震颤/Tremor、破裂/Rupture、沉沦/Sinking、蓄力/Poise

## ⚙️ 配置项

在 AstrBot 配置中可设置：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `top_k` | 检索返回的 chunk 数量 | 6 |
| `chunk_size` | 分块大小（字符） | 800 |
| `overlap` | 分块重叠（字符） | 120 |
| `group_boost` | 群覆盖库加权系数 | 1.2 |
| `use_embedding` | 是否使用嵌入模型进行语义检索 | false |
| `use_reranking` | 是否使用重排序模型优化结果 | false |
| `webui_enabled` | 是否启用 WebUI | true |
| `webui_host` | WebUI 监听地址 | 0.0.0.0 |
| `webui_port` | WebUI 端口 | 8765 |
| `webui_token` | WebUI 访问 Token | 自动生成 |

## 🏗️ 知识库架构

```
知识库
├── 全局库 (global)
│   └── 通过 WebUI 上传
│   └── 所有群共享
└── 群覆盖库 (group)
    └── 通过 /guide import 导入
    └── 仅本群可用
    └── 检索时优先级更高
```

## 📄 API 参考

### REST API（需要 Token 认证）

```bash
# 获取状态
curl -H "Authorization: Bearer <token>" http://localhost:8765/stats

# 上传文档
curl -H "Authorization: Bearer <token>" \
  -F "file=@guide.txt" \
  -F "scope=global" \
  http://localhost:8765/docs/upload

# 搜索测试
curl -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "燃烧队配置", "top_k": 6}' \
  http://localhost:8765/search

# 获取模板列表
curl -H "Authorization: Bearer <token>" http://localhost:8765/templates

# 保存自定义模板
curl -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "我的模板", "content": "模板内容...", "description": "模板描述"}' \
  http://localhost:8765/templates

# 获取状态映射列表
curl -H "Authorization: Bearer <token>" http://localhost:8765/status-mappings

# 添加状态映射
curl -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"status_name": "rupture", "subcategory": "被动破裂", "display_name": "非破裂但有破裂效果"}' \
  http://localhost:8765/status-mappings
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📜 许可证

MIT License
