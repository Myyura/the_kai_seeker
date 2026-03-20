"""Structured chat session state reducer and prompt renderer."""

import json
import re
from copy import deepcopy
from typing import Any

MAX_RECENT_USER_REQUESTS = 8
MAX_COMPLETED_WORK = 20
MAX_PENDING_ACTIONS = 10
MAX_OPEN_QUESTIONS = 10
MAX_RECENT_TURNS = 10
MAX_SOURCES = 20
MAX_VISITED_PAGES = 20
MAX_PDFS = 20
MAX_SCHOOL_SEARCHES = 10
MAX_QUESTION_SEARCHES = 10
MAX_FETCHED_QUESTIONS = 12
MAX_PDF_QUERIES = 12
MAX_NOTES = 20


class SessionStateService:
    def default_state(self) -> dict[str, Any]:
        return {
            "version": 1,
            "goal": {
                "core_user_need": "",
                "current_focus": "",
                "recent_user_requests": [],
            },
            "progress": {
                "completed_work": [],
                "pending_actions": [],
                "open_questions": [],
                "last_assistant_summary": "",
                "recent_turns": [],
            },
            "artifacts": {
                "sources": [],
                "visited_pages": [],
                "pdfs": [],
                "school_searches": [],
                "question_searches": [],
                "fetched_questions": [],
                "pdf_queries": [],
                "notes": [],
            },
        }

    def load(self, payload: str | dict[str, Any] | None) -> dict[str, Any]:
        state = self.default_state()
        data: dict[str, Any] = {}

        if isinstance(payload, str) and payload.strip():
            try:
                loaded = json.loads(payload)
            except json.JSONDecodeError:
                loaded = {}
            if isinstance(loaded, dict):
                data = loaded
        elif isinstance(payload, dict):
            data = payload

        self._merge_defaults(state, data)
        return state

    def dump(self, state: dict[str, Any]) -> str:
        return json.dumps(state, ensure_ascii=False)

    def rebuild_from_history(self, messages: list[Any], runs: list[Any]) -> dict[str, Any]:
        state = self.default_state()
        user_messages = [
            m for m in messages if getattr(m, "role", None) == "user" and m.content.strip()
        ]
        if user_messages:
            state["goal"]["core_user_need"] = user_messages[0].content.strip()
            state["goal"]["current_focus"] = user_messages[-1].content.strip()
            for message in user_messages[-MAX_RECENT_USER_REQUESTS:]:
                self._append_unique_text(
                    state["goal"]["recent_user_requests"],
                    message.content.strip(),
                    limit=MAX_RECENT_USER_REQUESTS,
                )

        assistant_by_id = {
            message.id: message
            for message in messages
            if getattr(message, "role", None) == "assistant"
        }
        processed_user_ids: set[int] = set()
        lower_bound = 0

        for run in sorted(runs, key=self._run_sort_key):
            assistant_message_id = getattr(run, "assistant_message_id", None)
            user_message = self._find_user_for_run(messages, assistant_message_id, lower_bound)
            if user_message is not None:
                processed_user_ids.add(user_message.id)
            if assistant_message_id is not None:
                lower_bound = max(lower_bound, assistant_message_id)

            assistant_message = assistant_by_id.get(assistant_message_id)
            tool_entries = self.extract_tool_entries_from_run(run)
            self.record_turn_outcome(
                state,
                user_request=user_message.content if user_message is not None else "",
                assistant_message=assistant_message.content
                if assistant_message is not None
                else "",
                tool_entries=tool_entries,
                status=getattr(run, "status", "completed"),
            )

        for message in user_messages:
            if message.id not in processed_user_ids:
                self.record_user_turn(state, message.content)

        return state

    def record_user_turn(self, state: dict[str, Any], user_message: str) -> dict[str, Any]:
        text = user_message.strip()
        if not text:
            return state

        goal = state["goal"]
        progress = state["progress"]
        if not goal["core_user_need"]:
            goal["core_user_need"] = text
        goal["current_focus"] = text
        self._append_unique_text(
            goal["recent_user_requests"],
            text,
            limit=MAX_RECENT_USER_REQUESTS,
        )
        self._append_unique_text(
            progress["pending_actions"],
            text,
            limit=MAX_PENDING_ACTIONS,
        )
        return state

    def record_turn_outcome(
        self,
        state: dict[str, Any],
        *,
        user_request: str,
        assistant_message: str,
        tool_entries: list[dict[str, Any]],
        status: str,
    ) -> dict[str, Any]:
        if user_request.strip():
            self.record_user_turn(state, user_request)

        progress = state["progress"]
        errors: list[str] = []
        tools_used: list[str] = []

        for entry in tool_entries:
            tool_name = entry.get("tool") or ""
            if tool_name:
                tools_used.append(tool_name)
            self._apply_tool_memory(state, entry)

            work_items = self._build_completed_work_items(entry)
            for item in work_items:
                self._append_unique_text(
                    progress["completed_work"],
                    item,
                    limit=MAX_COMPLETED_WORK,
                )

            if entry.get("success") is False:
                error = entry.get("error_message") or self._preview(
                    entry.get("result", ""), limit=240
                )
                if error:
                    errors.append(f"{tool_name}: {error}")
                    self._append_unique_text(
                        progress["open_questions"],
                        f"Resolve {tool_name} failure: {error}",
                        limit=MAX_OPEN_QUESTIONS,
                    )

        cleaned_user_request = user_request.strip()
        if status == "completed" and cleaned_user_request:
            progress["pending_actions"] = [
                item for item in progress["pending_actions"] if item != cleaned_user_request
            ]

        if assistant_message.strip():
            progress["last_assistant_summary"] = self._preview(assistant_message, limit=320)

        if cleaned_user_request or tools_used or assistant_message.strip():
            turn = {
                "user_request": cleaned_user_request,
                "status": status,
                "tools_used": self._dedupe_keep_order(tools_used),
                "assistant_summary": self._preview(assistant_message, limit=240),
                "errors": errors,
            }
            progress["recent_turns"].append(turn)
            progress["recent_turns"] = progress["recent_turns"][-MAX_RECENT_TURNS:]

        return state

    def record_failure(
        self,
        state: dict[str, Any],
        *,
        user_request: str,
        error_message: str,
    ) -> dict[str, Any]:
        if user_request.strip():
            self.record_user_turn(state, user_request)

        message = self._preview(error_message, limit=240)
        if message:
            self._append_unique_text(
                state["progress"]["open_questions"],
                f"Resolve failed run: {message}",
                limit=MAX_OPEN_QUESTIONS,
            )

        state["progress"]["recent_turns"].append(
            {
                "user_request": user_request.strip(),
                "status": "failed",
                "tools_used": [],
                "assistant_summary": "",
                "errors": [message] if message else [],
            }
        )
        state["progress"]["recent_turns"] = state["progress"]["recent_turns"][-MAX_RECENT_TURNS:]
        return state

    def render_prompt_block(self, state: dict[str, Any]) -> str:
        goal = state["goal"]
        progress = state["progress"]
        artifacts = state["artifacts"]

        sections = ["## Session State"]
        sections.append(self._render_list_section("Core user need", [goal["core_user_need"]]))
        sections.append(self._render_list_section("Current focus", [goal["current_focus"]]))
        sections.append(
            self._render_list_section(
                "Recent user requests",
                goal["recent_user_requests"],
            )
        )
        sections.append(
            self._render_list_section(
                "Completed work",
                progress["completed_work"],
            )
        )
        sections.append(
            self._render_list_section(
                "Pending actions",
                progress["pending_actions"],
            )
        )
        sections.append(
            self._render_list_section(
                "Open questions and unresolved issues",
                progress["open_questions"],
            )
        )
        sections.append(
            self._render_list_section(
                "Recent turn summaries",
                [self._format_turn_summary(turn) for turn in progress["recent_turns"]],
            )
        )
        sections.append(
            self._render_list_section(
                "Known official sources",
                [self._format_source(source) for source in artifacts["sources"]],
            )
        )
        sections.append(
            self._render_list_section(
                "Visited pages",
                [self._format_visited_page(page) for page in artifacts["visited_pages"]],
            )
        )
        sections.append(
            self._render_list_section(
                "Tracked PDFs",
                [self._format_pdf(pdf) for pdf in artifacts["pdfs"]],
            )
        )
        sections.append(
            self._render_list_section(
                "School search memory",
                [self._format_school_search(item) for item in artifacts["school_searches"]],
            )
        )
        sections.append(
            self._render_list_section(
                "Question search memory",
                [self._format_question_search(item) for item in artifacts["question_searches"]],
            )
        )
        sections.append(
            self._render_list_section(
                "Fetched question memory",
                [self._format_fetched_question(item) for item in artifacts["fetched_questions"]],
            )
        )
        sections.append(
            self._render_list_section(
                "PDF detail queries",
                [self._format_pdf_query(item) for item in artifacts["pdf_queries"]],
            )
        )
        sections.append(
            self._render_list_section(
                "Other notes",
                artifacts["notes"],
            )
        )
        return "\n\n".join(section for section in sections if section)

    def extract_tool_entries_from_run(self, run: Any) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for event in getattr(run, "events", []):
            payload = self._parse_payload(getattr(event, "payload", None))
            if payload.get("type") != "tool.finished":
                continue
            tool_name = payload.get("tool_name")
            if not tool_name:
                continue
            entries.append(
                {
                    "tool": tool_name,
                    "args": payload.get("args", {})
                    if isinstance(payload.get("args"), dict)
                    else {},
                    "result": payload.get("tool_result")
                    or payload.get("tool_result_preview")
                    or payload.get("error_message", ""),
                    "success": bool(payload.get("success", True)),
                    "error_message": payload.get("error_message"),
                }
            )
        return entries

    def _apply_tool_memory(self, state: dict[str, Any], entry: dict[str, Any]) -> None:
        tool = entry.get("tool")
        raw_result = entry.get("result", "")
        args = entry.get("args", {}) if isinstance(entry.get("args"), dict) else {}
        artifacts = state["artifacts"]

        if tool == "lookup_source":
            parsed = self._parse_json(raw_result)
            if isinstance(parsed, list):
                for source in parsed:
                    if not isinstance(source, dict):
                        continue
                    normalized = {
                        "id": source.get("id", ""),
                        "name": source.get("name", ""),
                        "category": source.get("category", ""),
                        "school_id": source.get("school_id"),
                        "urls": source.get("urls", {})
                        if isinstance(source.get("urls"), dict)
                        else {},
                    }
                    self._upsert_dict(
                        artifacts["sources"],
                        normalized,
                        identity=normalized.get("id") or normalized.get("name"),
                        limit=MAX_SOURCES,
                    )
            return

        if tool == "web_fetch":
            parsed = self._parse_json(raw_result)
            if isinstance(parsed, dict):
                url = parsed.get("url") or args.get("url") or ""
                page = {
                    "url": url,
                    "summary": self._extract_page_summary(parsed.get("markdown", "")),
                    "links": self._normalize_url_list(parsed.get("links")),
                    "pdf_links": self._normalize_url_list(parsed.get("pdf_links")),
                }
                self._upsert_dict(
                    artifacts["visited_pages"],
                    page,
                    identity=url or self._preview(page["summary"], limit=120),
                    limit=MAX_VISITED_PAGES,
                )
            return

        if tool in {"fetch_pdf_and_upload", "process_and_summarize_pdf"}:
            for pdf in self._extract_pdf_entries(raw_result):
                self._upsert_dict(
                    artifacts["pdfs"],
                    pdf,
                    identity=str(pdf.get("pdf_id", "")),
                    limit=MAX_PDFS,
                )
            return

        if tool == "query_pdf_details":
            for item in self._extract_pdf_query_entries(raw_result):
                self._upsert_dict(
                    artifacts["pdf_queries"],
                    item,
                    identity=f"{item.get('pdf_id')}::{item.get('question')}",
                    limit=MAX_PDF_QUERIES,
                )
            return

        if tool == "search_schools":
            parsed = self._parse_json(raw_result)
            if isinstance(parsed, list):
                item = {
                    "query": args.get("query"),
                    "results": [
                        self._compact_school_result(row)
                        for row in parsed[:6]
                        if isinstance(row, dict)
                    ],
                }
                self._upsert_dict(
                    artifacts["school_searches"],
                    item,
                    identity=args.get("query") or "__all__",
                    limit=MAX_SCHOOL_SEARCHES,
                )
            return

        if tool == "search_questions":
            parsed = self._parse_json(raw_result)
            if isinstance(parsed, list):
                item = {
                    "filters": {k: v for k, v in args.items() if v not in (None, "", [])},
                    "results": [
                        self._compact_question_result(row)
                        for row in parsed[:8]
                        if isinstance(row, dict)
                    ],
                }
                identity = json.dumps(item["filters"], sort_keys=True, ensure_ascii=False)
                self._upsert_dict(
                    artifacts["question_searches"],
                    item,
                    identity=identity or "__all__",
                    limit=MAX_QUESTION_SEARCHES,
                )
            return

        if tool == "fetch_question":
            item = self._extract_fetched_question_entry(raw_result, args)
            if item:
                self._upsert_dict(
                    artifacts["fetched_questions"],
                    item,
                    identity=item["question_id"],
                    limit=MAX_FETCHED_QUESTIONS,
                )
            return

        note = f"{tool}: {self._preview(raw_result, limit=220)}"
        self._append_unique_text(artifacts["notes"], note, limit=MAX_NOTES)

    def _build_completed_work_items(self, entry: dict[str, Any]) -> list[str]:
        tool = entry.get("tool")
        args = entry.get("args", {}) if isinstance(entry.get("args"), dict) else {}
        raw_result = entry.get("result", "")
        if entry.get("success") is False:
            return []

        if tool == "lookup_source":
            target = self._describe_filters(args)
            return [f"Looked up official sources{f' for {target}' if target else ''}."]

        if tool == "web_fetch":
            parsed = self._parse_json(raw_result)
            url = parsed.get("url") if isinstance(parsed, dict) else args.get("url")
            return (
                [f"Fetched and read web page {url}."] if url else ["Fetched and read a web page."]
            )

        if tool == "fetch_pdf_and_upload":
            items = self._extract_pdf_entries(raw_result)
            results = []
            for item in items:
                label = (
                    item.get("filename") or item.get("source_url") or f"pdf_id={item.get('pdf_id')}"
                )
                results.append(f"Fetched and processed PDF {label}.")
            return results or ["Fetched and processed a PDF."]

        if tool == "process_and_summarize_pdf":
            items = self._extract_pdf_entries(raw_result)
            results = []
            for item in items:
                label = item.get("filename") or f"pdf_id={item.get('pdf_id')}"
                results.append(f"Summarized PDF {label}.")
            return results or ["Summarized a PDF."]

        if tool == "query_pdf_details":
            question = args.get("question")
            if question:
                return [f"Queried PDF details for '{question}'."]
            return ["Queried PDF details."]

        if tool == "search_schools":
            query = args.get("query")
            return [f"Searched schools{f' for {query}' if query else ''}."]

        if tool == "search_questions":
            filters = self._describe_filters(args)
            return [f"Searched question database{f' with {filters}' if filters else ''}."]

        if tool == "fetch_question":
            question_id = args.get("question_id")
            return [f"Fetched question {question_id}."] if question_id else ["Fetched a question."]

        if tool == "echo":
            return ["Ran the echo tool."]

        return [f"Executed tool {tool}."]

    def _extract_pdf_entries(self, raw_result: str) -> list[dict[str, Any]]:
        parsed = self._parse_json(raw_result)
        if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
            items = parsed["results"]
        elif isinstance(parsed, dict):
            items = [parsed]
        else:
            items = []

        extracted: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            pdf_id = item.get("pdf_id")
            if pdf_id is None:
                continue
            extracted.append(
                {
                    "pdf_id": pdf_id,
                    "filename": item.get("filename"),
                    "source_url": item.get("source_url"),
                    "status": item.get("status"),
                    "summary": self._preview(item.get("summary_markdown", ""), limit=500),
                    "image_pages": item.get("image_pages", [])
                    if isinstance(item.get("image_pages"), list)
                    else [],
                }
            )
        return extracted

    def _extract_pdf_query_entries(self, raw_result: str) -> list[dict[str, Any]]:
        parsed = self._parse_json(raw_result)
        if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
            items = parsed["results"]
        elif isinstance(parsed, dict):
            items = [parsed]
        else:
            items = []

        extracted: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("error"):
                continue
            pdf_id = item.get("pdf_id")
            question = item.get("question")
            snippets = item.get("snippets", []) if isinstance(item.get("snippets"), list) else []
            pages = [
                snippet.get("page")
                for snippet in snippets
                if isinstance(snippet, dict) and snippet.get("page") is not None
            ]
            preview = self._preview(
                "\n".join(
                    snippet.get("text", "") for snippet in snippets if isinstance(snippet, dict)
                ),
                limit=500,
            )
            extracted.append(
                {
                    "pdf_id": pdf_id,
                    "question": question,
                    "pages": pages,
                    "preview": preview,
                }
            )
        return extracted

    def _extract_fetched_question_entry(
        self, raw_result: str, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        question_id = args.get("question_id")
        if not question_id:
            return None

        source_url = None
        body = raw_result
        source_match = re.search(r"^Source:\s*(.+)$", raw_result, flags=re.MULTILINE)
        if source_match:
            source_url = source_match.group(1).strip()
        if "\n---\n" in raw_result:
            body = raw_result.split("\n---\n", 1)[1]
        return {
            "question_id": question_id,
            "source_url": source_url,
            "preview": self._preview(body, limit=500),
        }

    def _compact_school_result(self, row: dict[str, Any]) -> dict[str, Any]:
        departments = []
        for department in row.get("departments", [])[:4]:
            if not isinstance(department, dict):
                continue
            departments.append(
                {
                    "id": department.get("id"),
                    "name_ja": department.get("name_ja"),
                    "programs": [
                        {
                            "id": program.get("id"),
                            "name_ja": program.get("name_ja"),
                        }
                        for program in department.get("programs", [])[:4]
                        if isinstance(program, dict)
                    ],
                }
            )
        return {
            "id": row.get("id"),
            "name_ja": row.get("name_ja"),
            "departments": departments,
        }

    def _compact_question_result(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "title": row.get("title"),
            "school_id": row.get("school_id"),
            "department_id": row.get("department_id"),
            "program_id": row.get("program_id"),
            "year": row.get("year"),
            "tags": row.get("tags", []) if isinstance(row.get("tags"), list) else [],
            "kai_project_url": row.get("kai_project_url"),
        }

    def _extract_page_summary(self, markdown: str) -> str:
        text = markdown.strip()
        if not text:
            return ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""
        summary = " ".join(lines[:4])
        return self._preview(summary, limit=400)

    def _find_user_for_run(
        self,
        messages: list[Any],
        assistant_message_id: int | None,
        lower_bound: int,
    ) -> Any | None:
        if assistant_message_id is None:
            return None
        candidate = None
        for message in messages:
            if getattr(message, "id", 0) >= assistant_message_id:
                break
            if getattr(message, "id", 0) <= lower_bound:
                continue
            if getattr(message, "role", None) == "user":
                candidate = message
        return candidate

    def _run_sort_key(self, run: Any) -> tuple[str, int]:
        created_at = getattr(run, "created_at", None)
        return (created_at.isoformat() if created_at is not None else "", getattr(run, "id", 0))

    def _parse_payload(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if not isinstance(payload, str) or not payload.strip():
            return {}
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _parse_json(self, raw_result: str) -> Any:
        if not isinstance(raw_result, str) or not raw_result.strip():
            return None
        try:
            return json.loads(raw_result)
        except json.JSONDecodeError:
            return None

    def _render_list_section(self, title: str, items: list[str]) -> str:
        cleaned = [item for item in items if isinstance(item, str) and item.strip()]
        if not cleaned:
            return f"### {title}\n- None."
        lines = [f"### {title}"]
        lines.extend(f"- {item}" for item in cleaned)
        return "\n".join(lines)

    def _format_turn_summary(self, turn: dict[str, Any]) -> str:
        request = turn.get("user_request") or "(no request text captured)"
        status = turn.get("status") or "unknown"
        tools = ", ".join(turn.get("tools_used", [])) or "none"
        assistant_summary = turn.get("assistant_summary") or "no assistant summary"
        errors = "; ".join(turn.get("errors", []))
        line = f"[{status}] request={request} | tools={tools} | outcome={assistant_summary}"
        if errors:
            line += f" | errors={errors}"
        return line

    def _format_source(self, source: dict[str, Any]) -> str:
        urls = source.get("urls", {})
        url_part = ", ".join(
            f"{name}={url}" for name, url in urls.items() if isinstance(url, str) and url
        )
        meta = source.get("category") or "uncategorized"
        if source.get("school_id"):
            meta += f", school={source['school_id']}"
        return f"{source.get('name') or source.get('id')} ({meta}) | {url_part or 'no URLs'}"

    def _format_visited_page(self, page: dict[str, Any]) -> str:
        links = ", ".join(page.get("links", [])[:5]) or "no links"
        pdf_links = ", ".join(page.get("pdf_links", [])[:5]) or "no pdf links"
        summary = page.get("summary") or "no summary"
        return f"{page.get('url')} | summary={summary} | links={links} | pdf_links={pdf_links}"

    def _format_pdf(self, pdf: dict[str, Any]) -> str:
        parts = [f"pdf_id={pdf.get('pdf_id')}"]
        if pdf.get("filename"):
            parts.append(f"filename={pdf['filename']}")
        if pdf.get("status"):
            parts.append(f"status={pdf['status']}")
        if pdf.get("source_url"):
            parts.append(f"source={pdf['source_url']}")
        if pdf.get("summary"):
            parts.append(f"summary={pdf['summary']}")
        return " | ".join(parts)

    def _format_school_search(self, item: dict[str, Any]) -> str:
        schools = ", ".join(
            f"{row.get('id')}({row.get('name_ja')})" for row in item.get("results", [])
        )
        query = item.get("query") or "(all schools)"
        return f"query={query} | matches={schools or 'none'}"

    def _format_question_search(self, item: dict[str, Any]) -> str:
        filters = item.get("filters", {})
        filter_text = ", ".join(f"{k}={v}" for k, v in filters.items()) or "no filters"
        results = ", ".join(
            row.get("id") or row.get("title") or "unknown" for row in item.get("results", [])
        )
        return f"filters={filter_text} | results={results or 'none'}"

    def _format_fetched_question(self, item: dict[str, Any]) -> str:
        parts = [f"question_id={item.get('question_id')}"]
        if item.get("source_url"):
            parts.append(f"source={item['source_url']}")
        if item.get("preview"):
            parts.append(f"preview={item['preview']}")
        return " | ".join(parts)

    def _format_pdf_query(self, item: dict[str, Any]) -> str:
        parts = [f"pdf_id={item.get('pdf_id')}", f"question={item.get('question')}"]
        if item.get("pages"):
            parts.append(f"pages={','.join(str(page) for page in item['pages'])}")
        if item.get("preview"):
            parts.append(f"preview={item['preview']}")
        return " | ".join(parts)

    def _append_unique_text(self, items: list[str], value: str, *, limit: int) -> None:
        text = value.strip()
        if not text:
            return
        items[:] = [item for item in items if item != text]
        items.append(text)
        if len(items) > limit:
            del items[:-limit]

    def _upsert_dict(
        self,
        items: list[dict[str, Any]],
        item: dict[str, Any],
        *,
        identity: str | None,
        limit: int,
    ) -> None:
        key = identity or self._preview(json.dumps(item, ensure_ascii=False), limit=80)
        normalized = deepcopy(item)
        normalized["_key"] = key
        items[:] = [existing for existing in items if existing.get("_key") != key]
        items.append(normalized)
        if len(items) > limit:
            del items[:-limit]

    def _merge_defaults(self, target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if key not in target:
                target[key] = value
                continue
            if isinstance(target[key], dict) and isinstance(value, dict):
                self._merge_defaults(target[key], value)
                continue
            target[key] = value

    def _preview(self, text: Any, limit: int = 240) -> str:
        if not isinstance(text, str):
            return ""
        cleaned = " ".join(text.split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 1] + "…"

    def _describe_filters(self, args: dict[str, Any]) -> str:
        filters = [f"{key}={value}" for key, value in args.items() if value not in (None, "", [])]
        return ", ".join(filters)

    def _normalize_url_list(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized = []
        for value in values:
            if isinstance(value, str) and value:
                normalized.append(value)
        return self._dedupe_keep_order(normalized)[:10]

    def _dedupe_keep_order(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result
