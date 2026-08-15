# RAGForgeWidget — 智能客服聊天挂件

可嵌入任意网页的纯原生 JS 客服挂件，对接 RAG Forge 后端（`/session` + `/chat` 多轮会话）。零依赖、零构建工具，两行代码接入。

## 文件清单

| 文件 | 说明 |
|------|------|
| `widget.js` | 挂件逻辑。IIFE 封装，全局仅暴露 `window.RAGForgeWidget`；CSS 类名均带 `rf-` 前缀 |
| `widget.css` | 挂件样式。右下角气泡 → 展开 360×520 聊天窗；移动端（≤480px）自动全屏 |
| `demo.html` | 模拟「云帆 SaaS 平台」官网演示页，右下角嵌入挂件 |

## 快速开始

```bash
# 1. 启动后端（项目根目录）
ragforge serve                     # → http://127.0.0.1:8777

# 2. 启动演示页静态服务（widget/ 目录）
cd widget
python serve.py                     # 推荐：修正 Windows 下 .js 的 MIME 注册问题
# 或: python -m http.server 8080    # 也可以，浏览器无 nosniff 时同样能跑

# 3. 浏览器打开
#    http://localhost:8080/demo.html
```

> **不要直接双击 `demo.html`**（`file://` 协议）：浏览器对 `file://` 页面的跨域
> `fetch` 限制更严格（Origin 为 `null`），部分浏览器会直接拦截请求。演示请走
> 上面的静态服务方式。

## 配置

```js
new RAGForgeWidget({
  apiBase: 'http://localhost:8777',  // 后端地址，默认 http://localhost:8777
  apiKey: 'ragforge-dev-change-me',  // X-API-Key（后端 .env 的 RAGFORGE_API_KEY）
  title: '智能客服',                  // 窗口标题
  placeholder: '请输入问题…'          // 输入框占位
}).mount('#rf-widget-root');         // 挂到指定元素；不传参则自动注入 <body>
```

`apiKey` 的三种提供方式（优先级从高到低）：

1. URL 参数：`demo.html?apiKey=xxx&apiBase=http://localhost:8777`
2. 构造参数 `apiKey`
3. 留空 → 首次打开挂件弹出「连接设置」窗口，输入后存入 `localStorage`（键 `ragforge_widget_settings`），刷新不丢失；窗口右上角 ⚙ 可随时改

## 功能点

- **多轮会话**：首次打开自动 `POST /session` 创建会话，同一挂件实例复用 `session_id`，连续提问上下文连续；会话过期（404）自动重建并重试一次
- **grounded 徽标**：每条回答显示「有引用」（绿）/「无引用」（灰）；有引用时悬停徽标可见来源
- **转人工（UI 占位）**：无引用回答下方出现「转人工」按钮，点击提示"人工客服即将上线，已记录您的问题"。纯前端占位，不调后端
- **错误友好提示**：401/403 引导打开设置；429 限流提示；网络错误提示检查后端地址
- **中文输入安全**：处理 IME 组词状态，中文输入时回车不会误发送
- **请求超时**：120s（Agentic 链路多轮检索 + 生成耗时较长）

## 冒烟验证（QA 路径）

1. 静态服务起后打开 `demo.html` → 右下角出现气泡，控制台无报错
2. 点气泡展开 → 出现欢迎语，自动创建会话（无 key 则弹设置窗口，输入后自动连接）
3. 连续提问 3 轮（如"你们平台支持哪些部署方式？" → "第二种的具体要求呢？" → "它的价格呢？"）
4. 观察：回答显示正常、「有引用/无引用」徽标、轮次标记递增、第 2/3 轮能正确解析指代（上下文连贯）
5. 控制台执行 `Object.keys(window).filter(k => /rag/i.test(k))` → 只有 `RAGForgeWidget`

## 已知边界

- `session_id` 保存在挂件内存中，**刷新页面后会话重置**（key/base 因存 localStorage 不丢）
- 回答按纯文本渲染（防 XSS），不解析 Markdown
- 「转人工」为占位交互，未接后端工单系统（对应后端 T4 待做项）
