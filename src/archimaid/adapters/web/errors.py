from fastapi import Request
from fastapi.responses import HTMLResponse

from archimaid.adapters.web.render import render
from archimaid.domain.errors import (
    AlreadyExists,
    DanglingReference,
    DomainError,
    InvalidEntity,
    InvalidReferenceCode,
    NotFound,
    ReferenceInUse,
)


class UiError(Exception):
    """A domain error a form cannot show in place; rendered as a flash message or error page."""

    def __init__(self, error: DomainError) -> None:
        super().__init__(str(error))
        self.error = error


_STATUS: tuple[tuple[type[DomainError], int], ...] = (
    (NotFound, 404),
    (ReferenceInUse, 409),
    (AlreadyExists, 409),
    (InvalidEntity, 422),
    (InvalidReferenceCode, 422),
    (DanglingReference, 422),
)


def status_for(exc: DomainError) -> int:
    for cls, status in _STATUS:
        if isinstance(exc, cls):
            return status
    return 500


def inline_problem(exc: DomainError) -> tuple[list[str], int]:
    """Messages and status for errors a form shows in place; the rest become a UiError."""
    if isinstance(exc, NotFound | ReferenceInUse):
        raise UiError(exc) from exc
    return [str(exc)], status_for(exc)


async def ui_error_handler(request: Request, exc: UiError) -> HTMLResponse:
    status = status_for(exc.error)
    message = str(exc.error)
    if request.headers.get("HX-Request"):
        return render(
            request,
            "_flash.html",
            status_code=status,
            headers={"HX-Retarget": "#flash", "HX-Reswap": "innerHTML"},
            message=message,
        )
    return render(request, "error.html", status_code=status, message=message, code=status)
