# RAG Forge

**企业级模块化 RAG 管线** — Python LangGraph 六阶段 Pipeline，企业特性内置，MIT 协议。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 六阶段 Pipeline

```
INGEST → CHUNK → EMBED → INDEX → RETRIEVE → RERANK → GENERATE → EVALUATE
```

每个节点是独立函数，可单独替换和测试。

## 快速开始

```bash
pip install -e .

# 写入环境变量
cp .env.example .env   # 编辑 DEEPSEEK_API_KEY

# 入库文档
ragforge ingest ./docs/

# 提问
ragforge ask "项目架构是怎样的"

# 启动 API
ragforge serve
```

## 核心特性

| 特性 | 说明 |
|------|------|
| **模块化 Pipeline** | LangGraph StateGraph，8 个节点可单独替换 |
| **混合检索** | 稠密向量 + BM25 关键词 → RRF 融合 |
| **Rerank 精排** | Cross-encoder 二次排序提升精度 |
| **嵌入指纹缓存** | md5 去重，同一文档二次入库零 Embedding 成本 |
| **多租户隔离** | 所有操作 tenant_id 隔离，API Key 鉴权 |
| **审计日志** | 结构化 JSONL，ingest/query 全记录 |
| **速率限制** | Token bucket，per-tenant 限流 |
| **RAGAS 评估** | faithfulness / answer_relevancy / context_precision |
| **CLI + API** | `ragforge ingest/ask/serve` + FastAPI REST |

## API

```bash
# 启动服务
ragforge serve

# 入库
curl -X POST http://localhost:8777/ingest \
  -H "X-API-Key: ragforge-dev-change-me" \
  -H "Content-Type: application/json" \
  -d '{"paths": ["./docs/README.md"], "tenant_id": "default"}'

# 提问
curl -X POST http://localhost:8777/ask \
  -H "X-API-Key: ragforge-dev-change-me" \
  -H "Content-Type: application/json" \
  -d '{"question": "什么是 RAG Forge", "tenant_id": "default"}'
```

## 架构

```
src/ragforge/
├── pipeline.py         # LangGraph StateGraph 核心
├── config.py           # 环境配置
├── cli.py              # Click CLI
├── ingestion/          # 解析器 + 切分器
├── indexing/           # Embedding + 向量存储
├── retrieval/          # 混合检索 + Rerank
├── generation/         # LLM 生成 + 引用
├── evaluation/         # RAGAS 评估
├── cache/              # 嵌入指纹缓存
├── enterprise/         # 多租户 / 鉴权 / 审计 / 限流
└── api/                # FastAPI 应用
```

## 设计决策

- **LangGraph 而非 LangChain LCEL** — 状态图更适合多阶段管线，内置 Checkpointer 支持断点恢复
- **Chroma 默认** — 零配置开箱即用，可接任何 OpenAI 兼容向量存储
- **JSON 嵌入缓存** — < 10K 条目用 JSON 足够，换 SQLite 需条目 > 50K
- **CLI 优先** — 对齐 Unix 管道哲学，API 是附加接口
- **MIT 协议** — 无需担心 AGPL 传染

## License

MIT © 李胜
