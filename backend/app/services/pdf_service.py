import base64
import logging
import re
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.base import ChatMessage
from app.providers.factory import create_provider
from app.repositories.pdf_repo import PdfRepository
from app.repositories.provider_repo import ProviderRepository

logger = logging.getLogger(__name__)

MIN_TEXT_LEN_FOR_TEXT_PAGE = 40
CHUNK_SIZE = 1200


class PdfService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PdfRepository(session)
        self.provider_repo = ProviderRepository(session)

    @property
    def upload_dir(self) -> Path:
        p = Path("./data/uploads/pdfs").resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    async def save_upload(self, filename: str, content: bytes) -> dict:
        temp_path = str(self.upload_dir / f"tmp_{filename}")
        doc = await self.repo.create_document(filename=filename, storage_path=temp_path, status="uploaded")
        final_path = self.upload_dir / f"{doc.id}.pdf"
        final_path.write_bytes(content)
        await self.repo.update_document(doc.id, status="uploaded")
        doc.storage_path = str(final_path)
        await self.session.commit()
        await self.session.refresh(doc)
        return {
            "pdf_id": doc.id,
            "filename": doc.filename,
            "status": doc.status,
        }

    async def process_and_summarize(self, pdf_id: int, focus: str | None = None) -> dict:
        doc = await self.repo.get_document(pdf_id)
        if doc is None:
            raise ValueError(f"PDF not found: {pdf_id}")

        await self.repo.update_document(pdf_id, status="processing")

        pages = self._extract_pages(Path(doc.storage_path))
        image_pages = [p["page"] for p in pages if p["is_image_page"]]

        if image_pages:
            ocr_map = await self._ocr_image_pages(Path(doc.storage_path), image_pages)
            for page_data in pages:
                page = page_data["page"]
                if page in ocr_map and ocr_map[page].strip():
                    page_data["text"] = (page_data["text"] + "\n" + ocr_map[page]).strip()

        full_text = "\n\n".join([f"[Page {p['page']}]\n{p['text']}" for p in pages if p["text"].strip()])
        chunks = self._build_chunks(pages)
        await self.repo.replace_chunks(pdf_id, chunks)

        summary = await self._summarize_text(full_text, focus=focus)
        await self.repo.update_document(
            pdf_id,
            status="processed",
            summary_markdown=summary,
            extracted_text=full_text,
        )

        return {
            "pdf_id": pdf_id,
            "status": "processed",
            "image_pages": image_pages,
            "summary_markdown": summary,
        }

    async def query_details(self, pdf_id: int, question: str, top_k: int = 4) -> dict:
        doc = await self.repo.get_document(pdf_id, with_chunks=True)
        if doc is None:
            raise ValueError(f"PDF not found: {pdf_id}")
        if not doc.chunks:
            raise ValueError("PDF has not been processed yet. Please run process_and_summarize_pdf first.")

        q_tokens = self._tokenize(question)
        scored: list[tuple[float, int, str]] = []
        for c in doc.chunks:
            c_tokens = self._tokenize(c.content)
            overlap = len(q_tokens & c_tokens)
            bonus = min(len(c.content) / 1200.0, 1.0)
            score = overlap + bonus
            if score > 0:
                scored.append((score, c.page_number, c.content))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = scored[:max(1, top_k)] if scored else []
        snippets = [
            {"page": page, "text": text[:700]} for _, page, text in selected
        ]

        return {
            "pdf_id": pdf_id,
            "question": question,
            "snippets": snippets,
        }

    async def list_admin_documents(
        self,
        *,
        query: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        return await self.repo.list_documents(query=query, status=status, limit=limit)

    async def get_admin_document_detail(self, pdf_id: int) -> dict:
        doc = await self.repo.get_document(pdf_id, with_chunks=True)
        if doc is None:
            raise ValueError(f"PDF not found: {pdf_id}")

        references = await self.repo.list_document_references(pdf_id)
        extracted_text = doc.extracted_text or ""

        return {
            "id": doc.id,
            "filename": doc.filename,
            "status": doc.status,
            "storage_path": doc.storage_path,
            "storage_exists": Path(doc.storage_path).exists(),
            "summary_markdown": doc.summary_markdown,
            "extracted_text_preview": self._preview_text(extracted_text, limit=3000),
            "extracted_text_length": len(extracted_text),
            "chunk_count": len(doc.chunks),
            "referenced_sessions": references,
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
        }

    async def get_admin_document_chunks(self, pdf_id: int, limit: int = 40) -> dict:
        doc = await self.repo.get_document(pdf_id)
        if doc is None:
            raise ValueError(f"PDF not found: {pdf_id}")

        chunks = await self.repo.search_chunks(pdf_id)
        selected = chunks[:limit]
        return {
            "pdf_id": pdf_id,
            "count": len(chunks),
            "chunks": [
                {
                    "id": chunk.id,
                    "page_number": chunk.page_number,
                    "content_preview": self._preview_text(chunk.content, limit=500),
                    "content_length": len(chunk.content),
                }
                for chunk in selected
            ],
        }

    async def delete_document(self, pdf_id: int) -> None:
        doc = await self.repo.get_document(pdf_id)
        if doc is None:
            raise ValueError(f"PDF not found: {pdf_id}")

        storage_path = Path(doc.storage_path)
        deleted = await self.repo.delete_document(pdf_id)
        if not deleted:
            raise ValueError(f"PDF not found: {pdf_id}")

        try:
            if storage_path.exists():
                storage_path.unlink()
        except OSError as exc:
            logger.warning("Failed to remove PDF file %s: %s", storage_path, exc)

    def _extract_pages(self, pdf_path: Path) -> list[dict]:
        try:
            import fitz  # type: ignore
        except Exception:
            return self._extract_pages_with_pypdf(pdf_path)

        pages: list[dict] = []
        with fitz.open(str(pdf_path)) as doc:
            for idx, page in enumerate(doc, start=1):
                text = page.get_text("text") or ""
                image_count = len(page.get_images(full=True))
                is_image_page = len(text.strip()) < MIN_TEXT_LEN_FOR_TEXT_PAGE and image_count > 0
                pages.append({
                    "page": idx,
                    "text": text.strip(),
                    "is_image_page": is_image_page,
                })
        return pages

    def _extract_pages_with_pypdf(self, pdf_path: Path) -> list[dict]:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(pdf_path))
        pages: list[dict] = []
        for idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            pages.append({"page": idx, "text": text, "is_image_page": len(text) < MIN_TEXT_LEN_FOR_TEXT_PAGE})
        return pages

    async def _ocr_image_pages(self, pdf_path: Path, image_pages: list[int]) -> dict[int, str]:
        if not image_pages:
            return {}
        try:
            import fitz  # type: ignore
        except Exception:
            return {}

        ocr_map: dict[int, str] = {}
        with fitz.open(str(pdf_path)) as doc:
            for page_num in image_pages:
                page = doc[page_num - 1]
                pix = page.get_pixmap(dpi=220)
                png_bytes = pix.tobytes("png")
                text = await self._ocr_with_provider(png_bytes)
                if text:
                    ocr_map[page_num] = text
        return ocr_map

    async def _ocr_with_provider(self, image_bytes: bytes) -> str:
        active = await self.provider_repo.get_active()
        if active is None:
            return ""

        if active.provider in {"openai", "deepseek", "openai-compatible"}:
            base_url = (active.base_url or "https://api.openai.com/v1").rstrip("/")
            url = f"{base_url}/chat/completions"
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            body = {
                "model": active.model or "gpt-4o-mini",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract all visible text and tables from this page."},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                        ],
                    }
                ],
                "temperature": 0,
            }
            try:
                async with httpx.AsyncClient(timeout=90) as client:
                    resp = await client.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {active.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning("OCR call failed: %s", e)
                return ""

        return ""

    async def _summarize_text(self, full_text: str, focus: str | None = None) -> str:
        if not full_text.strip():
            return "# PDF Summary\n\nNo extractable text found in this PDF."

        active = await self.provider_repo.get_active()
        if active is None:
            return self._fallback_summary(full_text)

        provider = create_provider(active)
        truncated = full_text[:20000]
        prompt = (
            "Summarize this admission-related PDF into markdown with sections: "
            "Basic Info, Key Timeline, Requirements, Important Reminders. "
            "Cite relevant page numbers when visible in content tags like [Page N]."
        )
        if focus:
            prompt += f" Focus particularly on: {focus}."

        try:
            response = await provider.chat([
                ChatMessage(role="system", content="You are a precise document summarizer."),
                ChatMessage(role="user", content=f"{prompt}\n\n{truncated}"),
            ])
            return response.content.strip() or self._fallback_summary(full_text)
        except Exception:
            logger.exception("Summary LLM call failed; using fallback summary")
            return self._fallback_summary(full_text)

    def _build_chunks(self, pages: list[dict]) -> list[tuple[int, str]]:
        chunks: list[tuple[int, str]] = []
        for p in pages:
            text = p["text"].strip()
            if not text:
                continue
            segments = re.split(r"\n{2,}", text)
            for seg in segments:
                seg = seg.strip()
                if not seg:
                    continue
                if len(seg) <= CHUNK_SIZE:
                    chunks.append((p["page"], seg))
                    continue
                for i in range(0, len(seg), CHUNK_SIZE):
                    chunks.append((p["page"], seg[i : i + CHUNK_SIZE]))
        return chunks

    def _fallback_summary(self, full_text: str) -> str:
        lines = [line.strip() for line in full_text.splitlines() if line.strip()][:20]
        preview = "\n".join(f"- {line[:160]}" for line in lines)
        return (
            "# PDF Summary\n\n"
            "## Basic Info\n"
            "- Parsed locally from uploaded PDF.\n\n"
            "## Key Extracted Lines\n"
            f"{preview}\n"
        )

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        tokens = re.findall(r"[\w\u3040-\u30ff\u4e00-\u9fff]+", text.lower())
        return {t for t in tokens if len(t) >= 2}

    @staticmethod
    def _preview_text(text: str, limit: int = 500) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "…"
