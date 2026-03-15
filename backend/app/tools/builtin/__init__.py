from app.tools.builtin.echo import EchoTool
from app.tools.builtin.fetch_question import FetchQuestionTool
from app.tools.builtin.lookup_source import LookupSourceTool
from app.tools.builtin.process_and_summarize_pdf import ProcessAndSummarizePdfTool
from app.tools.builtin.query_pdf_details import QueryPdfDetailsTool
from app.tools.builtin.search_questions import SearchQuestionsTool
from app.tools.builtin.search_schools import SearchSchoolsTool
from app.tools.builtin.web_fetch import WebFetchTool
from app.tools.registry import tool_registry


def register_builtin_tools() -> None:
    """Register all built-in tools into the global registry."""
    tool_registry.register(EchoTool())
    tool_registry.register(WebFetchTool())
    tool_registry.register(SearchSchoolsTool())
    tool_registry.register(SearchQuestionsTool())
    tool_registry.register(FetchQuestionTool())
    tool_registry.register(LookupSourceTool())
    tool_registry.register(ProcessAndSummarizePdfTool())
    tool_registry.register(QueryPdfDetailsTool())
