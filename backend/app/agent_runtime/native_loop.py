"""Native AgentRuntime tool loop internals."""

import asyncio
import datetime
import json
import logging
import re
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from app.agent_runtime.types import ToolCallRecord, ToolLoopResult
from app.providers.base import BaseLLMProvider, ChatResponse, ProviderMessage
from app.services.domain_config import domain_config
from app.tool_runtime.execution import ToolExecutionService
from app.tools.registry import tool_registry

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_FORMAT_REPAIRS = 2

FORMAT_REPAIR_PROMPT = (
    "Your previous response did not match the required JSON contract. "
    "Return ONLY one valid JSON object with keys: response_type, assistant_text, "
    "turn_summary, tool_call. Do not include markdown fences or extra commentary."
)


class StructuredToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class StructuredModelTurn(BaseModel):
    response_type: str
    assistant_text: str = ""
    turn_summary: str = ""
    tool_call: StructuredToolCall | None = None


class NativeLoopError(Exception):
    def __init__(
        self,
        message: str,
        *,
        tool_calls: list[ToolCallRecord] | None = None,
        usage: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.tool_calls = tool_calls or []
        self.usage = usage
        self.cause = cause
        self.error_type = cause.__class__.__name__ if cause is not None else self.__class__.__name__
        self.error_message = str(cause) if cause is not None else message


async def run_native_agent_loop(
    provider: BaseLLMProvider,
    messages: list[ProviderMessage],
    allowed_tool_names: set[str] | None = None,
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> ToolLoopResult:
    tool_call_log: list[ToolCallRecord] = []
    usage: dict[str, Any] | None = None
    max_tool_turns = domain_config.max_tool_turns
    tool_executor = ToolExecutionService(provider=provider)

    try:
        for turn in range(max_tool_turns):
            if on_event:
                await on_event(
                    {
                        "type": "status",
                        "status": "thinking",
                        "label": "Thinking",
                        "detail": "Planning the next step",
                    }
                )

            structured, response_usage = await _request_structured_turn(provider, messages)
            usage = _merge_usage(usage, response_usage)

            if structured.response_type == "final":
                assistant_text = structured.assistant_text.strip()
                turn_summary = _normalize_turn_summary(structured.turn_summary, assistant_text)
                return ToolLoopResult(
                    assistant_text=assistant_text,
                    turn_summary=turn_summary,
                    tool_calls=tool_call_log,
                    usage=usage,
                )

            tool_call = structured.tool_call
            if tool_call is None:
                raise ValueError("Structured tool_call response missing tool_call payload.")

            tool_name = tool_call.name
            tool_args = tool_call.arguments
            tool = tool_registry.get(tool_name)
            tool_display_name = tool.display_name if tool else tool_name
            tool_activity_label = tool.activity_label if tool else tool_display_name
            tool_call_id = f"tool-{turn + 1}"
            started_at = datetime.datetime.now(datetime.timezone.utc)

            logger.info("Agent tool call [turn %d]: %s(%s)", turn + 1, tool_name, tool_args)

            if on_event:
                await on_event(
                    {
                        "type": "tool.started",
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "tool_display_name": tool_display_name,
                        "tool_activity_label": tool_activity_label,
                        "args": tool_args,
                    }
                )

            record = await tool_executor.execute(
                tool_name=tool_name,
                arguments=tool_args,
                allowed_tool_names=allowed_tool_names,
                call_id=tool_call_id,
                display_name=tool_display_name,
                activity_label=tool_activity_label,
                started_at=started_at,
            )
            tool_call_log.append(record)

            if on_event:
                primary_pdf_resource = _extract_pdf_resource(record)
                await on_event(
                    {
                        "type": "tool.finished",
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "tool_display_name": tool_display_name,
                        "tool_activity_label": tool_activity_label,
                        "args": tool_args,
                        "artifacts": _summarize_artifacts(record),
                        "success": record.success,
                        "error_message": record.error_text,
                        "resource": primary_pdf_resource,
                    }
                )

            messages.append(
                ProviderMessage(
                    role="assistant",
                    content=json.dumps(
                        {
                            "response_type": "tool_call",
                            "assistant_text": "",
                            "turn_summary": "",
                            "tool_call": {
                                "name": tool_name,
                                "arguments": tool_args,
                            },
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            messages.append(
                ProviderMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "response_type": "tool_result",
                            "tool_output": record.output,
                        },
                        ensure_ascii=False,
                    ),
                )
            )

            if _should_stop_after_repeated_pdf_no_match(tool_call_log, record):
                assistant_text, turn_summary = _build_pdf_no_match_final(record)
                return ToolLoopResult(
                    assistant_text=assistant_text,
                    turn_summary=turn_summary,
                    tool_calls=tool_call_log,
                    usage=usage,
                )

        logger.warning("Agent reached max tool turns (%d)", max_tool_turns)
        structured, response_usage = await _request_structured_turn(provider, messages)
        usage = _merge_usage(usage, response_usage)
        if structured.response_type != "final":
            raise ValueError("Agent reached max tool turns without producing a final answer.")
        assistant_text = structured.assistant_text.strip()
        turn_summary = _normalize_turn_summary(structured.turn_summary, assistant_text)
        return ToolLoopResult(
            assistant_text=assistant_text,
            turn_summary=turn_summary,
            tool_calls=tool_call_log,
            usage=usage,
        )
    except Exception as exc:
        if isinstance(exc, NativeLoopError):
            raise
        raise NativeLoopError(
            str(exc),
            tool_calls=list(tool_call_log),
            usage=usage,
            cause=exc,
        ) from exc


async def _request_structured_turn(
    provider: BaseLLMProvider,
    messages: list[ProviderMessage],
) -> tuple[StructuredModelTurn, dict[str, Any] | None]:
    attempt_messages = list(messages)
    usage: dict[str, Any] | None = None

    for attempt in range(MAX_FORMAT_REPAIRS + 1):
        response = await _chat_with_retry(provider, attempt_messages, structured=True)
        usage = _merge_usage(usage, response.usage)
        structured = _parse_structured_turn(response.content)
        if structured is not None:
            return structured, usage
        if attempt == MAX_FORMAT_REPAIRS:
            break
        logger.warning("Model returned invalid structured response: %s", response.content)
        attempt_messages.extend(
            [
                ProviderMessage(role="assistant", content=response.content),
                ProviderMessage(role="user", content=FORMAT_REPAIR_PROMPT),
            ]
        )

    raise ValueError("Model returned an invalid structured response.")


async def _chat_with_retry(
    provider: BaseLLMProvider,
    messages: list[ProviderMessage],
    *,
    structured: bool = False,
) -> ChatResponse:
    for attempt in range(MAX_RETRIES):
        try:
            if structured:
                return await provider.chat_json(messages)
            return await provider.chat(messages)
        except Exception as exc:
            if attempt == MAX_RETRIES - 1:
                raise
            logger.warning(
                "LLM call failed (attempt %d/%d): %s — retrying in %ds",
                attempt + 1,
                MAX_RETRIES,
                exc,
                RETRY_DELAY,
            )
            await asyncio.sleep(RETRY_DELAY)
    raise RuntimeError("unreachable")


def _parse_structured_turn(text: str) -> StructuredModelTurn | None:
    json_text = _extract_json_object(text)
    if json_text is None:
        return None
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    normalized = {
        "response_type": payload.get("response_type")
        or payload.get("type")
        or payload.get("action")
        or "",
        "assistant_text": payload.get("assistant_text")
        or payload.get("answer")
        or payload.get("content")
        or "",
        "turn_summary": payload.get("turn_summary") or payload.get("summary") or "",
        "tool_call": payload.get("tool_call") or payload.get("call"),
    }
    try:
        structured = StructuredModelTurn.model_validate(normalized)
    except Exception:
        return None

    response_type = structured.response_type.strip().lower()
    if response_type not in {"final", "tool_call"}:
        return None
    structured.response_type = response_type

    if response_type == "tool_call":
        if structured.tool_call is None or not structured.tool_call.name.strip():
            return None
        return structured

    if not structured.assistant_text.strip():
        return None
    structured.turn_summary = _normalize_turn_summary(
        structured.turn_summary,
        structured.assistant_text,
    )
    return structured


def _extract_json_object(text: str) -> str | None:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    while start >= 0:
        candidate = _balanced_json_object(stripped, start)
        if candidate is not None:
            return candidate
        start = stripped.find("{", start + 1)
    return None


def _balanced_json_object(text: str, start: int) -> str | None:
    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _normalize_turn_summary(turn_summary: str, assistant_text: str) -> str:
    cleaned = " ".join((turn_summary or "").split())
    if cleaned:
        return cleaned
    fallback = " ".join((assistant_text or "").split())
    if len(fallback) <= 120:
        return fallback
    return fallback[:119] + "…"


def _should_stop_after_repeated_pdf_no_match(
    tool_call_log: list[ToolCallRecord],
    record: ToolCallRecord,
) -> bool:
    current = _pdf_no_match_signature(record)
    if current is None:
        return False

    for previous in reversed(tool_call_log[:-1]):
        previous_signature = _pdf_no_match_signature(previous)
        if previous_signature is None:
            continue
        if current["pdf_scope"] != previous_signature["pdf_scope"]:
            continue
        if _questions_are_similar(current["question"], previous_signature["question"]):
            return True
    return False


def _pdf_no_match_signature(record: ToolCallRecord) -> dict[str, Any] | None:
    if record.tool_name != "query_pdf_details" or not record.success or not record.artifacts:
        return None

    pdf_ids: list[int] = []
    question = str(record.arguments.get("question") or "").strip()
    no_match_flags: list[bool] = []

    for artifact in record.artifacts:
        if artifact.kind != "pdf_query":
            continue
        locator = artifact.locator or {}
        no_match_flags.append(bool(locator.get("no_match")))
        pdf_id = locator.get("pdf_id")
        if isinstance(pdf_id, int):
            pdf_ids.append(pdf_id)
        if not question and isinstance(locator.get("question"), str):
            question = locator["question"].strip()

    if not no_match_flags or not all(no_match_flags):
        return None

    return {
        "question": question,
        "pdf_scope": tuple(sorted(set(pdf_ids))),
    }


def _questions_are_similar(left: str, right: str) -> bool:
    left_text = " ".join(left.split()).lower()
    right_text = " ".join(right.split()).lower()
    if not left_text or not right_text:
        return False
    if left_text == right_text or left_text in right_text or right_text in left_text:
        return True

    left_tokens = _question_tokens(left_text)
    right_tokens = _question_tokens(right_text)
    if not left_tokens or not right_tokens:
        return False

    overlap = len(left_tokens & right_tokens)
    if overlap == 0:
        return False
    jaccard = overlap / len(left_tokens | right_tokens)
    containment = max(overlap / len(left_tokens), overlap / len(right_tokens))
    return jaccard >= 0.5 or containment >= 0.75


def _question_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w\u3040-\u30ff\u4e00-\u9fff]+", text.lower())
        if len(token) >= 2
    }


def _build_pdf_no_match_final(record: ToolCallRecord) -> tuple[str, str]:
    signature = _pdf_no_match_signature(record) or {}
    question = str(signature.get("question") or record.arguments.get("question") or "").strip()
    pdf_scope = signature.get("pdf_scope") or ()
    pdf_text = ""
    if pdf_scope:
        pdf_label = ", ".join(str(pdf_id) for pdf_id in pdf_scope)
        pdf_text = f" PDF {pdf_label}"

    if _looks_japanese(question):
        assistant_text = (
            f"現在の{pdf_text or 'PDF'}で「{question or 'この内容'}」を2回検索しましたが、明確に一致する記述は見つかりませんでした。"
            "募集要項に直接書かれていないか、別の公式表現で記載されている可能性があります。"
            "次は原文に近いキーワードに変えるか、ページ範囲を絞るか、関連する公式ページや添付資料を確認するのがよいです。"
        )
        turn_summary = f"現在の PDF では「{question or 'この内容'}」に一致する記述が見つからなかった。"
        return assistant_text, turn_summary

    if _looks_cjk(question):
        assistant_text = (
            f"我连续两次在当前{pdf_text or ' PDF'}里检索“{question or '这个问题'}”，都没有找到明确匹配的片段。"
            "这通常意味着文档里没有直接写出这项信息，或者使用了不同的官方表述。"
            "建议下一步改用更接近原文的关键词、指定更具体的页码范围，或转去查询对应的官方网页/附件。"
        )
        turn_summary = f"当前 PDF 未找到与“{question or '该问题'}”直接匹配的片段。"
        return assistant_text, turn_summary

    assistant_text = (
        f"I queried the current{pdf_text or ' PDF'} twice for "
        f"'{question or 'this question'}' and still found no matching snippets. "
        "That usually means the document does not state it explicitly, or it uses different wording. "
        "The next best step is to try the exact official phrasing, narrow the page range, "
        "or check the related official web page or attachment."
    )
    turn_summary = f"No matching PDF snippets found for '{question or 'this question'}'."
    return assistant_text, turn_summary


def _looks_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text))


def _looks_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff]", text))


def _merge_usage(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not left:
        return dict(right) if right else None
    if not right:
        return left

    merged = dict(left)
    for key, value in right.items():
        if isinstance(value, (int, float)) and isinstance(merged.get(key), (int, float)):
            merged[key] = merged[key] + value
        elif isinstance(value, (int, float)) and key not in merged:
            merged[key] = value
        else:
            merged[key] = value
    return merged


def _summarize_artifacts(record: ToolCallRecord) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for artifact in record.artifacts:
        summaries.append(
            {
                "kind": artifact.kind,
                "label": artifact.label,
                "summary": artifact.summary,
                "locator": artifact.locator,
                "replay": artifact.replay,
            }
        )
    return summaries


def _extract_pdf_resource(record: ToolCallRecord) -> dict[str, Any] | None:
    for artifact in record.artifacts:
        if artifact.kind != "pdf_summary":
            continue
        locator = artifact.locator or {}
        pdf_id = locator.get("pdf_id")
        if pdf_id is None:
            continue
        return {
            "pdf_id": pdf_id,
            "filename": locator.get("filename"),
            "status": "processed",
            "source_url": locator.get("source_url"),
        }
    return None
