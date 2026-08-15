# RAG Forge 🔨

**企业级 Agentic RAG 引擎** —— LangGraph 驱动的自反思检索增强生成，带 Web 控制台、对比评估体系与企业特性。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Vue 3](https://img.shields.io/badge/frontend-Vue3-42b883.svg)](frontend/)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-1c3c3c.svg)](src/ragforge/agentic/)

RAG Forge 把经典 RAG 从"一次检索、一次生成"的确定性管线升级为**可决策、可反思、可审计**的 Agentic 系统：LLM 在检索链条上做出意图路由、相关性评分、查询改写、答案自检等决策，检索不足时自动改写重试，答案不 grounded 时自动复盘重查 —— 全程决策轨迹可审计。

---

## 🏗️ 系统架构

```
                        ┌────────────────────────────────────────────┐
                        │              Agentic 决策层                │
                        │                                            │
  用户问题 ──→ route 意图路由 ──direct──→ 直接回答                    │
                        │  │                                         │
                        │  └──clarify──→ 澄清+尽力回答               │
                        │  │                                         │
                        │  └──retrieve──→ grade_docs 相关性评分      │
                        │                    │          ↑            │
                        │              (无相关文档)    (改写后重查)   │
                        │                    ▼          │            │
                        │               rewrite 查询改写─┘   ≤3 轮    │
                        │                    │                        │
                        │                    ▼                        │
                        │              generate 生成回答              │
                        │                    │                        │
                        │                    ▼                        │
                        │              grade_answer 答案自检          │
                        │                    │          ↑            │
                        │          (不 grounded)   (改写后重查)       │
                        │                    ▼          │            │
                        │                 输出答案        └───────────┘
                        └────────────────────────────────────────────┘
                                        │ 复用
                                        ▼
                        ┌────────────────────────────────────────────┐
                        │           确定性 RAG 管线（8 节点）        │
                        │  INGEST→CHUNK→EMBED→INDEX→RETRIEVE→RERANK  │
                        │  →GENERATE→EVALUATE                        │
                        │  混合检索(dense+BM25→RRF) · Rerank · 缓存   │
                        └────────────────────────────────────────────┘
```

**两层设计**：确定性管线负责检索基建（混合检索、精排、缓存、多租户），Agentic 层在其上叠加 LLM 决策 —— 每层可独立替换、独立测试。

## 🤖 Agentic RAG 核心能力

| 能力 | 实现 | 效果 |
|------|------|------|
| **意图路由** | LLM 三路决策：检索 / 直接回答 / 澄清 | 闲聊不浪费检索，模糊问题不空手 |
| **相关性评分** | LLM 过滤无关文档（grade_docs） | 上下文精度 0.63 → 0.72+，减少幻觉 |
| **查询改写** | 检索不足时自动改写重查（≤3 轮） | 首轮失败自愈，不依赖用户重问 |
| **答案自检** | groundedness 检查（grade_answer） | 不 grounded 自动复盘，杜绝硬编造 |
| **澄清兜底** | clarify 路径带 best-effort 检索回答 | 模糊问题先给可用答案再要细节 |
| **引用校验** | 生成后 LLM 校验引用真实性 | 剔除幻觉引用，citations 可审计 |
| **增量索引** | DocumentHash 幂等入库：未变跳过、变更替换、删除精准 | 重复入库零成本，文档同步秒级 |
| **全程可审计** | 每一步决策写入 `trace` | 决策轨迹 API/CLI/前端全程可见 |

## 📊 对比评估（确定性 vs Agentic，LLM judge 打分）

12 题测试集（含 ground truth） × 双管线 × 六指标（faithfulness / answer_relevancy / usefulness / context_precision / **MRR / Hit@3**）：

| 指标 | 确定性 | Agentic | 说明 |
|------|:---:|:---:|------|
| **MRR** | 0.80 | **0.90** | 检索首命中质量，Agent 过滤后排名更准 |
| **Hit@3** | 0.8 | **0.9** | 期望文档进入 top3 的命中率 |
| **Context Precision** | 0.42 | **0.64** | Agentic 平均每问少喂 ~1.4 个噪声文档 |
| Faithfulness | 1.00 | 1.00 | 负样本零编造（诚实回答"知识库无此信息"） |
| Answer Relevancy | 1.00 | 1.00 | 持平 |
| Usefulness | 0.88 | 0.84 | 持平（小知识库下基线已足够好） |

**关键发现**（评估驱动了 5 个真实 bug 修复）：
- 负样本下基线管线曾**编造**不存在的集成方案（Faith 0.00），Agentic 的 rewrite 循环确认"知识库确实没有"后诚实回答
- grade 截断 500→2000 字符修复：LLM judge 信息不足导致的文档误杀（Faith 0.00→1.00）
- 生成器 grounding 强化：抑制上下文之外的"知识填充"（Faith 0.70→1.00）
- Q4 审计日志题：基线 MRR 0.25（未命中）→ Agent 1.00（精准命中期望文档）

```bash
ragforge eval-compare eval_questions.jsonl   # 可复现，自动生成 markdown 报告
```

## 🖥️ Web 控制台（Vue 3）

浏览器打开 `http://127.0.0.1:8777` —— 六页完整应用：

- **💬 对话**：Agentic/标准双模式切换，决策轨迹时间线可视化（路由→检索→评分→改写→自检），grounded 徽标，来源引用
- **📚 知识库**：拖拽上传（自动解析→切分→向量化→入库），文档列表，一键清空
- **🗂 会话**：客服对话全量留痕，会话列表 + 完整对话详情（轮数/消息）
- **❓ 未命中**：Agent 确认答不上来的问题自动入库（知识库补料的直接依据）
- **🎫 工单**：转人工咨询闭环管理，"标记已解决"一键完结
- **⚙️ 系统**：健康状态、LLM/Embedding 配置摘要、API Key 管理

```
POST /session      → {session_id}                              # 创建会话
POST /chat         → {answer, trace, grounded, session_id, rounds}  # 多轮对话
GET  /sessions     → 会话列表          GET /sessions/{id} → 会话详情
GET  /missed-questions → 未命中问题    POST /tickets → 转人工工单
GET  /tickets      → 工单列表          PATCH /tickets/{id} → 标记已解决
POST /agent-ask    → {answer, trace, grounded, citations}      # 单轮 Agentic
POST /upload       → multipart 文件入库
GET  /documents    → 文档聚合列表      DELETE /documents → 清空
```

## 💬 智能客服升级（多轮会话 + 人机协同 + 运营闭环）

在 Agentic RAG 之上叠加会话层，从"单轮问答"升级为"有记忆、会转人工、懂运营"的智能客服：

| 能力 | 实现 | 效果 |
|------|------|------|
| **多轮会话** | SQLite 会话存储（`sessions`/`messages` 表）+ 最近 4 轮历史注入生成 prompt | 追问带上下文，不重复解释 |
| **指代消解** | 入口 contextualize：历史+当前问题压缩为自包含 query | "它有什么优点？" → "RAG 有什么优点？"，路由/检索/改写全受益 |
| **未命中收集** | 检索触顶 + 无相关文档 → 自动入库（显式信号，不依赖 grounded 判定） | 知识库补料有据可依，运营闭环 |
| **转人工工单** | 无答案时挂件提供"转人工"，工单表 + 状态流转 | 人机协同，咨询不丢失 |
| **可嵌入挂件** | `widget/` 纯原生 JS（IIFE 零污染、rf- 前缀防冲突），两行代码接入任意网页 | 一行 `<script>` 即得客服 |

**多轮评估（无记忆 vs 有记忆，3 场景 × 追问指代）**：

| 指标 | 无记忆 | 有记忆 |
|------|:---:|:---:|
| 直接回答（无澄清前缀） | **1/3** | **3/3** |
| 命中主题 | 3/3（靠 clarify 兜底猜测） | 3/3（直接命中） |

关键证据：指代追问（"它有什么优点？"/"那它的缓存机制呢？"）无记忆全部走澄清兜底（"您指的是哪个产品？"），甚至检索方向错误（"没有找到缓存机制说明"）；有记忆直接命中目标主题（Embedding 缓存路径、RAG 核心优点）。

```bash
PYTHONPATH=src python scripts/eval_multi_turn.py   # 可复现多轮评估
cd widget && python serve.py                       # 挂件演示 → http://localhost:8080/demo.html
```

## 🚀 快速开始

```bash
pip install -e .
cp .env.example .env          # 填 DEEPSEEK_API_KEY

# 命令行
ragforge ingest ./docs/                    # 入库
ragforge agent-ask "你的问题"               # Agentic 问答（带决策轨迹）
ragforge ask "你的问题"                     # 确定性问答
ragforge eval-compare eval_questions.jsonl # 对比评估

# Web 控制台
cd frontend && npm install && npm run build
ragforge serve                             # → http://127.0.0.1:8777
```

## 🔬 技术栈与设计决策

- **LangGraph StateGraph**：条件边 + 循环 + 轮次预算（防死循环），状态全程可追踪
- **混合检索**：稠密向量（bge-small-zh）+ BM25 → RRF 融合，中文按字分词零依赖
- **依赖注入架构**：LLM/retriever/reranker/generator 全部可注入 → 测试零网络零向量库
- **评估闭环**：LLM-as-judge（DeepSeek）按 RAGAS 语义打分，`eval-compare` 一键复现
- **多租户隔离**：tenant_id 级向量库隔离 + API Key 鉴权 + 审计日志 + 限流
- **单端口部署**：Vue 构建产物由 FastAPI 托管，Docker 一容器搞定

```
src/ragforge/
├── agentic/        # Agentic 决策层（路由/改写/评分/自检/contextualizer）
├── session/        # 会话存储（SQLite，多轮记忆 + 未命中 + 工单）
├── pipeline.py     # 确定性 RAG 管线（8 节点 LangGraph）
├── ingestion/      # 解析器 + 切分器
├── indexing/       # Embedding + 向量存储（Chroma/Qdrant）
├── retrieval/      # 混合检索 + Rerank
├── generation/     # LLM 生成 + 引用
├── evaluation/     # LLM judge 对比评估
├── enterprise/     # 多租户 / 鉴权 / 审计 / 限流
└── api/            # FastAPI + SPA 托管
frontend/           # Vue 3 控制台（对话/知识库/会话/未命中/工单/系统）
widget/             # 可嵌入客服挂件（原生 JS，两行接入）
tests/              # 46 个测试（Agentic 决策 + 混合检索 + 会话 + 未命中 + 工单）
```

## ✅ 质量验证

- **18/18 pytest 全绿**：Agentic 决策循环（改写/自检/预算兜底/clarify）+ 检索单元 + DocumentHash 增量索引
- **浏览器实操验收**：上传→问答→轨迹→清空 全流程
- **对比评估可复现**：12 题带 ground truth 测试集 + MRR/Hit@3 检索指标 + 自动报告

## License

MIT © 李胜
