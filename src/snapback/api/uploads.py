"""What may be uploaded to a case, checked on the server.

Three layers:

1. `UploadSizeGuard` refuses an upload from its Content-Length alone, before any of the body
   is read.
2. `parse_form` reads the body as it arrives and stops the moment one file passes the per-file
   cap or there are too many files. An oversized file is never spooled to disk in full.
3. `read_images` checks each file that did arrive: declared as an image, and starts like one.
"""

from fastapi import HTTPException, Request
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MB = 1024 * 1024
FORM_OVERHEAD = MB  # room for the text fields and the multipart framing


class FileTooLarge(MultiPartException):
    """One uploaded file passed the per-file cap while it was still arriving."""


class CappedMultiPartParser(MultiPartParser):
    """Starlette's multipart parser, with a cap on each file enforced as the bytes come in."""

    def __init__(self, headers, stream, *, max_files: int, max_file_bytes: int) -> None:
        super().__init__(headers, stream, max_files=max_files, max_fields=20)
        self._max_file_bytes = max_file_bytes
        self._file_bytes = 0

    def on_part_begin(self) -> None:
        super().on_part_begin()
        self._file_bytes = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self._file_bytes += end - start
            if self._file_bytes > self._max_file_bytes:
                raise FileTooLarge("file too large")
        super().on_part_data(data, start, end)


async def parse_form(request: Request, max_photos: int, max_file_bytes: int) -> FormData:
    """The request's form, read with the upload caps applied while it streams."""
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("multipart/form-data"):
        # Text fields only. The size guard let up to a full upload through; a form with no
        # files has no business being that large.
        if int(request.headers.get("content-length", "0")) > FORM_OVERHEAD:
            raise HTTPException(status_code=413, detail="The text is too long to accept.")
        return await request.form()

    parser = CappedMultiPartParser(
        request.headers, request.stream(), max_files=max_photos, max_file_bytes=max_file_bytes
    )
    try:
        return await parser.parse()
    except FileTooLarge:
        raise HTTPException(
            status_code=413, detail=f"Each photo can be at most {max_file_bytes // MB} MB."
        ) from None
    except MultiPartException as error:
        if error.message.startswith("Too many files"):
            raise HTTPException(
                status_code=413, detail=f"At most {max_photos} photos per check."
            ) from None
        if "exceeded maximum size" in error.message:
            raise HTTPException(status_code=413, detail="The text is too long to accept.") from None
        raise HTTPException(status_code=400, detail="The upload could not be read.") from None


def _looks_like_an_image(head: bytes) -> bool:
    if head.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a")):
        return True
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return True
    # HEIC, HEIF and AVIF from phones: an ISO media file whose brand says so.
    return head[4:8] == b"ftyp" and head[8:12] in (
        b"heic",
        b"heix",
        b"hevc",
        b"heim",
        b"heis",
        b"mif1",
        b"msf1",
        b"heif",
        b"avif",
    )


def read_images(photos: list[UploadFile], max_photos: int, max_bytes: int) -> list[bytes]:
    """The uploaded files as bytes, or an HTTP error naming what was wrong."""
    if len(photos) > max_photos:
        raise HTTPException(status_code=413, detail=f"At most {max_photos} photos per check.")
    images = []
    for photo in photos:
        if not (photo.content_type or "").startswith("image/"):
            raise HTTPException(status_code=415, detail="Only images can be uploaded.")
        data = photo.file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=413, detail=f"Each photo can be at most {max_bytes // MB} MB."
            )
        if not _looks_like_an_image(data[:16]):
            raise HTTPException(status_code=415, detail="Only images can be uploaded.")
        images.append(data)
    return images


class UploadSizeGuard:
    """Refuse `POST /cases` bodies that are too large, or of unknown length, unread."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] == "/cases":
            length = dict(scope["headers"]).get(b"content-length")
            refusal = None
            if length is None or not length.isdigit():
                refusal = JSONResponse(
                    {"detail": "Send a Content-Length with the upload."}, status_code=411
                )
            elif int(length) > self.max_body_bytes:
                refusal = JSONResponse(
                    {"detail": "The upload is too large to accept."}, status_code=413
                )
            if refusal is not None:
                await refusal(scope, receive, send)
                return
        await self.app(scope, receive, send)
