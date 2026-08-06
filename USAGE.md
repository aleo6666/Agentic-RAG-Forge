# RAG Forge 使用说明

## 安装

```bash
git clone <repo-url> rag-forge
cd rag-forge
pip install -e .
```

核心依赖会自动安装。如需本地 Embedding（无需 API Key），额外装：

```bash
pip install langgraph sentence-transformers chromadb rank-bm25
```

## 环境配置

```bash
cp .env.example .env
```

编辑 `.env`，填入 LLM API Key：

```env
# 必填：LLM（回答生成用）
DEEPSEEK_API_KEY=sk-your-key

# 可选：远程 Embedding（默认用本地模型，不填就自动下载）
# RAGFORGE_EMBED_PROVIDER=siliconflow
# SILICONFLOW_API_KEY=sk-your-key

# 可选：API 鉴权（默认自动生成开发 key）
# RAGFORGE_API_KEY=your-secret-key

# 可选：多租户 Key
# RAGFORGE_KEYS=key1:tenant-a:admin,key2:tenant-b:viewer
```

## CLI 命令

### 入库文档

```bash
# 默认段落策略
ragforge ingest ./docs/report.pdf ./notes/readme.md

# Markdown 标题切分策略（保持 #/##/### 章节完整）
ragforge ingest --strategy markdown ./docs/*.md

# 指定租户
ragforge ingest --tenant team-a ./team-a-docs/
```

### 提问

```bash
ragforge ask "项目使用了什么技术栈"

# 指定租户
ragforge ask --tenant team-a "上季度的销售额是多少"
```

### 启动 API 服务

```bash
ragforge serve                  # 默认 127.0.0.1:8777
ragforge serve --port 9000      # 自定义端口
ragforge serve --host 0.0.0.0   # 允许外部访问
```

## API 接口

### 健康检查

```bash
curl http://localhost:8777/health
# {"status":"ok","version":"0.1.0"}
```

### 入库

```bash
curl -X POST http://localhost:8777/ingest \
  -H "X-API-Key: ragforge-dev-xxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"paths": ["./docs/readme.md", "./docs/architecture.md"]}'

# 响应
# {"status":"ok","chunks":12,"documents":2}
```

### 提问

```bash
curl -X POST http://localhost:8777/ask \
  -H "X-API-Key: ragforge-dev-xxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"question": "RAG Forge 的 Pipeline 有几个阶段"}'

# 响应
# {
#   "answer": "RAG Forge 的 Pipeline 包含八个阶段...",
#   "citations": [{"source": "chunk_0", "snippet": "..."}],
#   "evaluation": {"faithfulness": 0.92, "answer_relevancy": 0.87}
# }
```

## Python SDK

```python
from ragforge import run_indexing, run_query, Document

# 入库
docs = [{"id": "doc1", "content": "RAG Forge 是一个模块化 RAG 管线", "metadata": {}}]
state = run_indexing(docs, tenant_id="default")
print(f"已索引 {len(state['chunks'])} 个 chunk")

# 提问
state = run_query("什么是 RAG Forge", tenant_id="default")
print(state["answer"])
for c in state["citations"]:
    print(f"  - {c['snippet']}")
```

## Docker 部署

```bash
docker compose up -d

# 验证
curl http://localhost:8777/health
```

## 多租户

每个 API Key 绑定一个租户。配置多个 Key：

```env
RAGFORGE_KEYS=sk-team-a:team-a:admin,sk-team-b:team-b:viewer
```

不同 Key 的入库和查询自动隔离，互不可见。

## 审计

所有入库和提问操作自动记录到 `audit.jsonl`：

```bash
tail -5 audit.jsonl
# {"timestamp":"2026-08-06T17:30:00","action":"ingest","tenant":"default","actor":"api","detail":"2 files"}
# {"timestamp":"2026-08-06T17:31:00","action":"ask","tenant":"default","actor":"api","detail":"什么是 RAG Forge"}
```

文件超过 10MB 自动轮转。

## 常见问题

**Q: 首次运行提示下载模型？**
A: 默认使用本地 Embedding 模型 `BAAI/bge-small-zh-v1.5`，首次运行会自动下载（约 100MB），之后缓存。

**Q: 如何切换到远程 Embedding？**
A: 在 `.env` 中设置 `RAGFORGE_EMBED_PROVIDER=siliconflow` 并填写 `SILICONFLOW_API_KEY`。

**Q: 提示 `No module named 'langgraph'`？**
A: `pip install langgraph`。LangGraph 是懒加载的，不影响其他模块使用。

**Q: 如何清空知识库？**
A: 删除 `./chroma_data/` 目录重建。

**Q: Embedding 缓存在哪？**
A: `./cache/embedding_cache.json`。同内容重新入库不会重复计算 Embedding。
