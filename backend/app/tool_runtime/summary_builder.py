import json
from typing import Any

from app.agent_runtime.types import ToolArtifact
from app.providers.base import BaseLLMProvider, ProviderMessage
from app.tools.base import ToolResult

LLM_SUMMARY_INPUT_LIMIT = 6000
GENERIC_TEXT_SUMMARY_LIMIT = 320


class ToolSummaryBuilder:
    """Build compact, replayable tool artifacts from raw tool results."""

    def __init__(self, provider: BaseLLMProvider | None = None):
        self.provider = provider

    async def build(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
    ) -> list[ToolArtifact]:
        if not result.success:
            return []

        raw_data = result.data
        json_data = self._coerce_json_like(raw_data)
        builders = {
            "lookup_source": self._build_lookup_source,
            "search_schools": self._build_search_schools,
            "search_questions": self._build_search_questions,
            "fetch_question": self._build_fetch_question,
            "web_fetch": self._build_web_fetch,
            "fetch_pdf_and_upload": self._build_pdf_summary,
            "process_and_summarize_pdf": self._build_pdf_summary,
            "query_pdf_details": self._build_pdf_query,
        }
        builder = builders.get(tool_name)
        if builder is not None:
            artifacts = builder(arguments=arguments, raw_data=raw_data, json_data=json_data)
            if artifacts:
                return artifacts

        generic = self._build_generic(tool_name=tool_name, arguments=arguments, raw_data=raw_data, json_data=json_data)
        if generic:
            return generic

        llm_artifact = await self._build_with_llm(
            tool_name=tool_name,
            arguments=arguments,
            raw_data=raw_data,
            json_data=json_data,
        )
        return [llm_artifact] if llm_artifact is not None else []

    def _build_lookup_source(
        self,
        *,
        arguments: dict[str, Any],
        raw_data: Any,
        json_data: Any,
    ) -> list[ToolArtifact]:
        if not isinstance(json_data, list):
            return []
        names = [self._format_source_name(item) for item in json_data[:4] if isinstance(item, dict)]
        query = arguments.get("query") or arguments.get("school_id") or arguments.get("category")
        label = f"Official source lookup for {query}" if query else "Official source lookup"
        summary = "Matched sources: " + ", ".join(names) if names else "Found official sources."
        return [
            ToolArtifact(
                kind="source_lookup",
                label=label,
                summary=summary,
                body_json=json_data,
                locator={k: v for k, v in arguments.items() if v not in (None, "", [])},
                replay={"tool_name": "lookup_source", "arguments": arguments},
                search_text=self._join_text([label, summary, json.dumps(json_data[:8], ensure_ascii=False)]),
            )
        ]

    def _build_search_schools(
        self,
        *,
        arguments: dict[str, Any],
        raw_data: Any,
        json_data: Any,
    ) -> list[ToolArtifact]:
        if not isinstance(json_data, list):
            return []
        titles = []
        for row in json_data[:4]:
            if not isinstance(row, dict):
                continue
            school = self._pick_text(row, "school_name", "label", "school_id", "name")
            department = self._pick_text(row, "department_name", "department_id")
            program = self._pick_text(row, "program_name", "program_id")
            parts = [part for part in [school, department, program] if part]
            if parts:
                titles.append(" / ".join(parts))
        query = arguments.get("query")
        label = f"School search for {query}" if query else "School search"
        summary = "Top matches: " + ", ".join(titles) if titles else "School search returned results."
        return [
            ToolArtifact(
                kind="school_search",
                label=label,
                summary=summary,
                body_json=json_data,
                locator={k: v for k, v in arguments.items() if v not in (None, "", [])},
                replay={"tool_name": "search_schools", "arguments": arguments},
                search_text=self._join_text([label, summary]),
            )
        ]

    def _build_search_questions(
        self,
        *,
        arguments: dict[str, Any],
        raw_data: Any,
        json_data: Any,
    ) -> list[ToolArtifact]:
        if not isinstance(json_data, list):
            return []
        titles = []
        for row in json_data[:4]:
            if not isinstance(row, dict):
                continue
            title = self._pick_text(row, "title", "id")
            year = row.get("year")
            tags = row.get("tags") if isinstance(row.get("tags"), list) else []
            suffix = f" ({year})" if year else ""
            tag_part = f" [{', '.join(str(tag) for tag in tags[:2])}]" if tags else ""
            if title:
                titles.append(f"{title}{suffix}{tag_part}")
        filters = {k: v for k, v in arguments.items() if v not in (None, "", [])}
        label = "Question search"
        summary = "Top matches: " + ", ".join(titles) if titles else "Question search returned results."
        return [
            ToolArtifact(
                kind="question_search",
                label=label,
                summary=summary,
                body_json=json_data,
                locator={"filters": filters},
                replay={"tool_name": "search_questions", "arguments": arguments},
                search_text=self._join_text([label, summary]),
            )
        ]

    def _build_fetch_question(
        self,
        *,
        arguments: dict[str, Any],
        raw_data: Any,
        json_data: Any,
    ) -> list[ToolArtifact]:
        if not isinstance(raw_data, str):
            return []
        lines = [line.strip() for line in raw_data.splitlines() if line.strip()]
        source_line = next((line for line in lines if line.startswith("Source:")), "")
        school_line = next((line for line in lines if line.startswith("School:")), "")
        body_lines = [line for line in lines if not line.startswith("Source:") and not line.startswith("School:") and line != "---"]
        question_id = arguments.get("question_id")
        label = question_id or "Fetched exam question"
        summary = self._preview(" ".join(body_lines[:5]), limit=GENERIC_TEXT_SUMMARY_LIMIT)
        locator = {"question_id": question_id}
        if source_line:
            locator["source"] = source_line.removeprefix("Source:").strip()
        if school_line:
            locator["school"] = school_line.removeprefix("School:").strip()
        return [
            ToolArtifact(
                kind="exam_question",
                label=label,
                summary=summary or "Fetched exam question content.",
                body_text=raw_data,
                locator=locator,
                replay={"tool_name": "fetch_question", "arguments": arguments},
                search_text=self._join_text([label, summary, school_line]),
            )
        ]

    def _build_web_fetch(
        self,
        *,
        arguments: dict[str, Any],
        raw_data: Any,
        json_data: Any,
    ) -> list[ToolArtifact]:
        if not isinstance(json_data, dict):
            return []
        markdown = self._pick_text(json_data, "markdown")
        title = None
        highlights: list[str] = []
        for line in markdown.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            if title is None and cleaned.startswith("#"):
                title = cleaned.lstrip("# ").strip()
            if any(token in cleaned.lower() for token in ["deadline", "exam", "admission", "募集", "出願", "試験", "資格"]):
                highlights.append(cleaned)
            if len(highlights) >= 3:
                break
        summary = " / ".join(highlights) or self._preview(markdown, limit=GENERIC_TEXT_SUMMARY_LIMIT)
        locator = {
            "url": json_data.get("url") or arguments.get("url"),
            "pdf_links": self._ensure_string_list(json_data.get("pdf_links"))[:6],
            "links": self._ensure_string_list(json_data.get("links"))[:12],
        }
        return [
            ToolArtifact(
                kind="web_page",
                label=title or locator["url"] or "Fetched web page",
                summary=summary or "Fetched web page content.",
                body_json=json_data if isinstance(raw_data, dict) else None,
                body_text=None if isinstance(raw_data, dict) else str(raw_data),
                locator=locator,
                replay={"tool_name": "web_fetch", "arguments": {"url": locator["url"]}},
                search_text=self._join_text([title or "", summary, locator.get("url", "")]),
            )
        ]

    def _build_pdf_summary(
        self,
        *,
        arguments: dict[str, Any],
        raw_data: Any,
        json_data: Any,
    ) -> list[ToolArtifact]:
        if isinstance(json_data, dict) and isinstance(json_data.get("results"), list):
            artifacts: list[ToolArtifact] = []
            for item in json_data["results"]:
                if not isinstance(item, dict):
                    continue
                artifacts.extend(self._build_pdf_summary(arguments=arguments, raw_data=item, json_data=item))
            return artifacts
        if not isinstance(json_data, dict):
            return []
        pdf_id = json_data.get("pdf_id")
        label = self._pick_text(json_data, "filename") or f"pdf:{pdf_id}" if pdf_id is not None else "Processed PDF"
        summary_markdown = self._pick_text(json_data, "summary_markdown")
        summary = self._preview(self._strip_markdown(summary_markdown), limit=GENERIC_TEXT_SUMMARY_LIMIT)
        locator = {
            "pdf_id": pdf_id,
            "filename": self._pick_text(json_data, "filename"),
            "source_url": self._pick_text(json_data, "source_url"),
        }
        replay_args = {"pdf_id": pdf_id} if pdf_id is not None else dict(arguments)
        if arguments.get("focus"):
            replay_args["focus"] = arguments["focus"]
        return [
            ToolArtifact(
                kind="pdf_summary",
                label=label,
                summary=summary or "Processed PDF summary available.",
                summary_format="markdown" if summary_markdown else "text",
                body_json=json_data if isinstance(raw_data, dict) else None,
                body_text=None if isinstance(raw_data, dict) else str(raw_data),
                locator=locator,
                replay={"tool_name": "process_and_summarize_pdf", "arguments": replay_args},
                search_text=self._join_text([label, summary, locator.get("source_url", "") or ""]),
            )
        ]

    def _build_pdf_query(
        self,
        *,
        arguments: dict[str, Any],
        raw_data: Any,
        json_data: Any,
    ) -> list[ToolArtifact]:
        if isinstance(json_data, dict) and isinstance(json_data.get("results"), list):
            artifacts: list[ToolArtifact] = []
            for item in json_data["results"]:
                if not isinstance(item, dict):
                    continue
                if item.get("error"):
                    continue
                artifacts.extend(self._build_pdf_query(arguments=arguments, raw_data=item, json_data=item))
            return artifacts
        if not isinstance(json_data, dict):
            return []
        snippets = json_data.get("snippets") if isinstance(json_data.get("snippets"), list) else []
        pages = [snippet.get("page") for snippet in snippets if isinstance(snippet, dict) and snippet.get("page") is not None]
        match_count = json_data.get("match_count")
        no_match = bool(json_data.get("no_match")) or len(snippets) == 0
        text_parts = [
            self._preview(self._pick_text(snippet, "text"), limit=120)
            for snippet in snippets[:3]
            if isinstance(snippet, dict)
        ]
        question = json_data.get("question") or arguments.get("question")
        pdf_id = json_data.get("pdf_id") or arguments.get("pdf_id")
        if no_match:
            pdf_part = f" in PDF {pdf_id}" if pdf_id is not None else ""
            question_part = f" for '{question}'" if question else ""
            summary = f"No matching snippets found{question_part}{pdf_part}."
        else:
            summary = " | ".join(part for part in text_parts if part) or "PDF query returned matching snippets."
        locator = {
            "pdf_id": pdf_id,
            "question": question,
            "pages": pages,
            "match_count": match_count if isinstance(match_count, int) else len(snippets),
            "no_match": no_match,
        }
        replay_args = {
            "question": locator["question"],
            "top_k": arguments.get("top_k", 4),
        }
        if locator["pdf_id"] is not None:
            replay_args["pdf_id"] = locator["pdf_id"]
        return [
            ToolArtifact(
                kind="pdf_query",
                label=f"PDF detail query for {locator['question']}" if locator.get("question") else "PDF detail query",
                summary=summary,
                body_json=json_data if isinstance(raw_data, dict) else None,
                body_text=None if isinstance(raw_data, dict) else str(raw_data),
                locator=locator,
                replay={"tool_name": "query_pdf_details", "arguments": replay_args},
                search_text=self._join_text([summary, json.dumps(locator, ensure_ascii=False)]),
            )
        ]

    def _build_generic(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        raw_data: Any,
        json_data: Any,
    ) -> list[ToolArtifact]:
        if isinstance(json_data, dict):
            summary = self._preview(json.dumps(json_data, ensure_ascii=False, sort_keys=True), limit=GENERIC_TEXT_SUMMARY_LIMIT)
            return [
                ToolArtifact(
                    kind="tool_output",
                    label=tool_name,
                    summary=summary,
                    body_json=json_data,
                    locator={"tool_name": tool_name},
                    replay={"tool_name": tool_name, "arguments": arguments},
                    search_text=self._join_text([tool_name, summary]),
                )
            ]
        if isinstance(json_data, list):
            preview = json.dumps(json_data[:4], ensure_ascii=False)
            return [
                ToolArtifact(
                    kind="tool_output_list",
                    label=tool_name,
                    summary=self._preview(preview, limit=GENERIC_TEXT_SUMMARY_LIMIT),
                    body_json=json_data,
                    locator={"tool_name": tool_name},
                    replay={"tool_name": tool_name, "arguments": arguments},
                    search_text=self._join_text([tool_name, preview]),
                )
            ]
        if isinstance(raw_data, str) and raw_data.strip():
            return [
                ToolArtifact(
                    kind="tool_output_text",
                    label=tool_name,
                    summary=self._preview(raw_data, limit=GENERIC_TEXT_SUMMARY_LIMIT),
                    body_text=raw_data,
                    locator={"tool_name": tool_name},
                    replay={"tool_name": tool_name, "arguments": arguments},
                    search_text=self._join_text([tool_name, raw_data[:800]]),
                )
            ]
        return []

    async def _build_with_llm(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        raw_data: Any,
        json_data: Any,
    ) -> ToolArtifact | None:
        if self.provider is None:
            return None
        source_text = ""
        if json_data is not None:
            source_text = json.dumps(json_data, ensure_ascii=False)
        elif isinstance(raw_data, str):
            source_text = raw_data
        if not source_text.strip():
            return None
        source_text = source_text[:LLM_SUMMARY_INPUT_LIMIT]
        try:
            response = await self.provider.chat_json(
                [
                    ProviderMessage(
                        role="system",
                        content=(
                            "Summarize a tool result for future retrieval. "
                            "Return JSON with keys: kind, label, summary. "
                            "Do not invent ids, urls, dates, or facts."
                        ),
                    ),
                    ProviderMessage(
                        role="user",
                        content=(
                            f"tool_name={tool_name}\n"
                            f"arguments={json.dumps(arguments, ensure_ascii=False)}\n"
                            f"tool_result={source_text}"
                        ),
                    ),
                ]
            )
            parsed = json.loads(response.content)
            if not isinstance(parsed, dict):
                return None
            summary = self._pick_text(parsed, "summary")
            if not summary:
                return None
            return ToolArtifact(
                kind=self._pick_text(parsed, "kind") or "tool_output",
                label=self._pick_text(parsed, "label") or tool_name,
                summary=summary,
                body_json=json_data if isinstance(json_data, (dict, list)) else None,
                body_text=raw_data if isinstance(raw_data, str) else None,
                locator={"tool_name": tool_name},
                replay={"tool_name": tool_name, "arguments": arguments},
                search_text=self._join_text([tool_name, summary]),
            )
        except Exception:
            return None

    @staticmethod
    def _format_source_name(item: dict[str, Any]) -> str:
        name = ToolSummaryBuilder._pick_text(item, "name", "id")
        school_id = item.get("school_id")
        return f"{name} ({school_id})" if name and school_id else name

    @staticmethod
    def _pick_text(source: Any, *keys: str) -> str:
        if not isinstance(source, dict):
            return ""
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _coerce_json_like(value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    def _ensure_string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if isinstance(item, (str, int, float)) and str(item).strip()]

    @staticmethod
    def _preview(text: str, *, limit: int) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 1] + "…"

    @staticmethod
    def _strip_markdown(text: str) -> str:
        stripped = text.replace("#", " ").replace("*", " ").replace("`", " ")
        return " ".join(stripped.split())

    @staticmethod
    def _join_text(parts: list[str]) -> str:
        return " | ".join(part for part in parts if part)
