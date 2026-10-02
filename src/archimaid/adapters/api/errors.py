from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from archimaid.domain.errors import (
    AlreadyExists,
    DanglingReference,
    DomainError,
    InvalidEntity,
    InvalidReferenceCode,
    NotFound,
    ReferenceInUse,
)

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    NotFound: 404,
    InvalidEntity: 422,
    InvalidReferenceCode: 422,
    DanglingReference: 422,
    ReferenceInUse: 409,
    AlreadyExists: 409,
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status = STATUS_BY_ERROR.get(type(exc), 500)
        return JSONResponse(status_code=status, content={"detail": str(exc)})
