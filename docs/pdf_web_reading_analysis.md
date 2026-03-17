# PDF 处理与网页读取流程分析（实现方案草案）

## 1) 当前代码流程梳理（上传 / 网页读取下载 / 解析 / 前端显示）

### 1.1 PDF 上传与处理
- 前端在 Chat 页支持两种上传入口：点击 `Upload PDF` 和拖拽上传，都会调用 `POST /files/upload`，并将返回的 `{pdf_id, filename}` 加入 `uploadedPdfs` 状态。 
- 后端 `files/upload` 会校验 Content-Type、文件大小和文件名，并调用 `PdfService.save_upload` 持久化到 `data/uploads/pdfs/{id}.pdf`。 
- PDF 的解析与摘要通过 `PdfService.process_and_summarize` 执行：
  - 优先使用 PyMuPDF 抽取文本 + 判断图片页；
  - 图片页可通过视觉模型 OCR；
  - 生成 chunks，写入 `pdf_chunks`；
  - 最终生成 `summary_markdown` 并写回 `pdf_documents`。

### 1.2 网页读取与 PDF 下载
- `web_fetch` 工具目前是用正则“去标签”变纯文本，输出字符串。它会去掉所有 HTML 标签，因此会丢失 `<a href="...">` 中的 URL。 
- `fetch_pdf_and_upload` 工具用于下载 PDF URL，然后复用 `PdfService.save_upload + process_and_summarize` 完成入库与解析。

### 1.3 前端显示
- 目前前端只显示“用户直接上传”的 PDF chip（`uploadedPdfs`）。
- agent 在工具链中通过 `fetch_pdf_and_upload` 下载的 PDF，不会自动并入 `uploadedPdfs`，因此用户看不到该 PDF 已被引用。

---

## 2) 需求 1：`web_fetch` 改为 HTML→Markdown，保留链接信息

### 2.1 问题根因
`web_fetch._html_to_text` 中 `re.sub(r"<[^>]+>", " ", text)` 会直接抹除标签结构，导致链接目标丢失；之后虽然有 HTML entity 解码，但链接已经不可恢复。

### 2.2 推荐实现（最小侵入）
1. 将 `web_fetch` 的核心转换逻辑替换为“HTML 转 Markdown”：
   - 首选库：`markdownify`（Python）或 `html2text`。
   - 保留超链接为 Markdown 形式：`[文本](URL)`。
2. 对输出做后处理：
   - 删除脚本/样式；
   - 限制最大长度（你现有 `MAX_CONTENT_LENGTH` 逻辑可保留）；
   - 可附加“发现的 PDF 链接列表”（如 `- https://...pdf`），便于模型精准调用 `fetch_pdf_and_upload`。
3. tool 描述更新：明确“返回 Markdown（保留链接）”。

### 2.3 建议伪代码
```python
from markdownify import markdownify as md

def _html_to_markdown(html: str) -> str:
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S|re.I)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S|re.I)
    text = md(html, heading_style="ATX", strip=["script", "style"])
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text
```

### 2.4 进阶增强（建议）
- 在 `web_fetch` 返回结构中加入：
  - `markdown`: 页面 Markdown；
  - `links`: 页面绝对链接数组（可选去重）；
  - `pdf_links`: 仅 PDF 链接数组。
- 这样 agent 不需要从长文本里二次抽取 URL，工具链鲁棒性更高。

---

## 3) 需求 2：统一组织“用户上传 + agent 抓取”PDF 的前端展示

### 3.1 目标交互
在输入框上方展示统一的“PDF 资源条”（圆角方框 chip）：
- 显示原始文件名（例如 `募集要項2026.pdf`）；
- 来源标记：`uploaded` / `fetched`；
- 状态标记：`uploaded` / `processing` / `processed` / `error`；
- 可移除（仅从当前会话上下文移除，不删除服务器文件）。

### 3.2 数据模型建议
前端将 `uploadedPdfs` 升级为 `chatPdfResources`：
```ts
type PdfResource = {
  pdf_id: number;
  filename: string;
  source: "uploaded" | "fetched";
  status: "uploaded" | "processing" | "processed" | "error";
  source_url?: string;
};
```

### 3.3 如何把 agent 抓取 PDF 同步到前端
当前 SSE 中已有 `tool_result` 事件，且对 `fetch_pdf_and_upload` 已特殊处理“不过度截断”。可在前端解析该 tool_result JSON：
1. 当 `tool_result === "fetch_pdf_and_upload"` 时，`JSON.parse(data.result)`；
2. 若 success，读取 `data.pdf_id`、`data.filename`、`data.status`；
3. 合并进 `chatPdfResources`（按 `pdf_id` 去重）；
4. 下次发消息时 `pdf_ids` 使用统一资源列表映射。

### 3.4 UI 布局建议
- 将 PDF chips 放在 textarea 上方独立一行（当前已接近该布局）；
- chip 使用圆角矩形（不是胶囊），更符合“文件标签”语义；
- 悬浮时展示来源和 URL（fetched 场景）；
- 超过一行可横向滚动或折叠“+N”。

---

## 4) 需求 3：现有流程中的明显缺陷与改进方案

### 4.1 明显缺陷 A：非流式聊天接口存在解包错误风险
`ChatService.chat` 返回四元组 `(content, model, sid, tool_call_log)`，但 `chat` 路由按三元组解包，存在运行时错误风险。

**改进**：
- 路由改为 `content, model, sid, _ = await service.chat(...)`；
- 或调整 `ChatService.chat` 只返回三元组，把 `tool_call_log` 放到可选字段或内部日志。

### 4.2 明显缺陷 B：前端会话切换后 PDF 上下文丢失
前端 `loadSession` 仅加载消息，不恢复该会话对应 PDF 资源，导致用户切回历史会话后看不到此前引用的 PDF chip。

**改进**：
- 后端新增会话资源接口（如 `GET /chat/sessions/{id}/pdfs`）；
- 聊天时记录“会话关联的 pdf_id 集合”；
- `loadSession` 同步拉取并恢复 chips。

### 4.3 明显缺陷 C：仅按 MIME 判断上传文件类型，兼容性较弱
浏览器上传 `file.content_type` 可能为空或非标准，当前会误拒绝。

**改进**：
- 允许 `content_type in {"application/pdf", "application/octet-stream", ""}`；
- 同时做文件头魔数校验（`%PDF-`）。

### 4.4 明显缺陷 D：`web_fetch` 正则解析 HTML 鲁棒性不足
正则无法稳定处理复杂 DOM、内联换行和实体，且会误删对 agent 有价值的信息（如链接）。

**改进**：
- 切换为 HTML parser + markdown converter；
- 输出结构化字段（markdown + pdf_links）。

### 4.5 明显缺陷 E：下载文件名来源单一
`fetch_pdf_and_upload` 仅用 URL path basename，可能得到乱码或 `download`。

**改进**：
- 优先解析 `Content-Disposition` filename；
- 其次回退 URL basename；
- 最后使用 `downloaded-{timestamp}.pdf`。

---

## 5) 推荐实施顺序（低风险增量）
1. **第一阶段（高收益）**：改 `web_fetch` 为 Markdown 输出 + 保留链接。
2. **第二阶段（体验）**：前端统一 `PdfResource`，接入 `fetch_pdf_and_upload` SSE 回填。
3. **第三阶段（一致性）**：补会话级 PDF 资源持久化与恢复。
4. **第四阶段（健壮性）**：修复 `chat` 非流式解包、上传 MIME/魔数、下载文件名推断。

---

## 6) 验收建议
- web_fetch 返回中可见 Markdown 链接：`[募集要項](https://...pdf)`。
- agent 能从 web_fetch 输出中提取并调用 `fetch_pdf_and_upload`。
- 用户上传 + agent 抓取的 PDF 都会在输入框上方 chip 展示，且显示原文件名。
- 切换会话后 chips 能恢复，发送消息时 `pdf_ids` 与 chips 一致。
- 非流式 `/chat/` 调用不再出现 tuple unpack 错误。

---

## 7) 关于“用 id 作为持久化文件名”是否会丢失原始名称

### 7.1 现状结论
当前策略是：
- 数据库存 `filename`（原始展示名）；
- 磁盘文件按 `{id}.pdf` 保存（稳定、避免重名覆盖）；

**因此“仅从系统数据完整性上看”，原始名称不会丢失**，因为前端展示和业务读取都可依赖 `pdf_documents.filename`。

### 7.2 潜在问题（需要改进）
虽然不直接丢名，但有几个隐患：
1. **语义混杂**：`filename` 同时承担“用户原始名”和“展示名”角色，后续若要做规范化、重命名、国际化展示会受限。
2. **抓取文件名质量波动**：`fetch_pdf_and_upload` 目前主要取 URL basename，可能出现 `download.pdf`、乱码名。
3. **缺少来源维度**：没有结构化记录 `source_type/uploaded_or_fetched`、`source_url`、`content_hash`，不利于去重和追溯。
4. **会话态与资源态解耦不足**：前端显示依赖临时状态，切会话后可能无法还原“当时参考了哪些 PDF”。

### 7.3 推荐升级方案（兼顾兼容性）
建议在不破坏现有 `id.pdf` 存储策略前提下，扩展元数据模型：

#### 数据层字段建议
- `original_filename`：上传时用户文件名 / 抓取时解析出的原始文件名。
- `display_name`：前端展示名（允许后续用户编辑）。
- `stored_filename`：真实磁盘名（如 `{id}.pdf`）。
- `source_type`：`uploaded | fetched`。
- `source_url`：抓取来源 URL（上传则为空）。
- `content_hash`：文件哈希（sha256）用于去重与缓存。

#### 读写策略建议
- 保存文件时继续使用 `id.pdf`（稳定、可控）。
- 前端 chip 一律显示 `display_name`，空则回退 `original_filename`。
- 抓取场景优先用 `Content-Disposition` 获取文件名，再回退 URL basename。

#### 迁移策略建议
1. 先加新字段（nullable），不删旧字段。
2. 批量回填：`original_filename = filename`，`display_name = filename`，`stored_filename = "{id}.pdf"`。
3. 服务层改读新字段，观察稳定后再考虑弱化旧 `filename`。

### 7.4 总结
你的当前策略（磁盘使用 id、数据库保存名称）是一个**可用且常见**的基础做法，不会天然丢失名称；
但如果你要实现“上传与抓取统一显示、可追溯、可去重、可持久化恢复”的目标，建议尽快升级为“**稳定存储名 + 独立展示名 + 来源元数据**”的模型。
