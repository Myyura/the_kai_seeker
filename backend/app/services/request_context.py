from contextlib import contextmanager
from contextvars import ContextVar

active_pdf_ids_var: ContextVar[list[int]] = ContextVar("active_pdf_ids", default=[])


@contextmanager
def set_active_pdf_ids(pdf_ids: list[int]):
    token = active_pdf_ids_var.set(pdf_ids)
    try:
        yield
    finally:
        active_pdf_ids_var.reset(token)


def get_active_pdf_ids() -> list[int]:
    return active_pdf_ids_var.get()
