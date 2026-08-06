# RAG Forge 项目文档

RAG Forge 是一个基于 LangGraph 的模块化 RAG 管线框架。

## 核心特性

- 八阶段 Pipeline：INGEST → CHUNK → EMBED → INDEX → RETRIEVE → RERANK → GENERATE → EVALUATE
- 混合检索：稠密向量 + BM25 关键词 → RRF 融合
- 嵌入指纹缓存：md5 去重，同一文档二次入库零 Embedding 成本
- 企业级内置：多租户隔离、API Key 鉴权、JSONL 审计日志、速率限制

## 技术栈

Python 3.11+, LangGraph, FastAPI, Chroma, DeepSeek API, Sentence-Transformers

## 许可证

MIT
