from pydantic import BaseModel


class PdfUploadOut(BaseModel):
    pdf_id: int
    filename: str
    status: str


class PdfProcessRequest(BaseModel):
    pdf_id: int
    focus: str | None = None


class PdfProcessOut(BaseModel):
    pdf_id: int
    status: str
    image_pages: list[int]
    summary_markdown: str


class PdfQueryRequest(BaseModel):
    pdf_id: int
    question: str
    top_k: int = 4


class PdfQueryOut(BaseModel):
    pdf_id: int
    question: str
    snippets: list[dict]
