"""Input model capturing the source of a pipeline run request."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .base import JsonModel

if TYPE_CHECKING:
    from werkzeug.datastructures import FileStorage


@dataclass
class InputFile(JsonModel):
    """Metadata about a single uploaded file.

    Stores only filename, content_type, and size_bytes — NOT raw bytes —
    to avoid bloating Firestore documents.
    """

    filename: str
    content_type: str
    size_bytes: int


@dataclass
class Input(JsonModel):
    """Describes the source input for a pipeline run.

    Attributes:
        mode:        One of "file", "text", or "doc_id".
        text:        The raw text content (when mode == "text").
        doc_id:      GCS document identifier (when mode == "doc_id").
        files:       List of file metadata objects (when mode == "file").
    """

    mode: str  # "file" | "text" | "doc_id"
    text: str | None = None
    doc_id: str | None = None
    files: list[InputFile] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Constructor helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_file_uploads(cls, uploads: list[Any]) -> "Input":
        """Create an Input from a list of werkzeug FileStorage objects.

        Reads each upload's stream to determine size_bytes, then resets the
        stream position with seek(0) so that downstream code (e.g. PDF-merge
        logic in simplify_v1_2.py) can still read the bytes.

        Args:
            uploads: List of werkzeug FileStorage objects. Each must expose
                     .filename, .content_type, and a readable .stream.

        Returns:
            Input instance with mode="file" and files populated.
        """
        input_files: list[InputFile] = []
        for upload in uploads:
            raw = upload.read()
            size_bytes = len(raw)
            upload.seek(0)
            input_files.append(
                InputFile(
                    filename=upload.filename or "",
                    content_type=upload.content_type or "",
                    size_bytes=size_bytes,
                )
            )
        return cls(mode="file", files=input_files)

    @classmethod
    def from_text(cls, text: str) -> "Input":
        """Create an Input from plain text.

        Args:
            text: The raw text content.

        Returns:
            Input instance with mode="text".
        """
        return cls(mode="text", text=text)

    @classmethod
    def from_doc_id(cls, doc_id: str) -> "Input":
        """Create an Input referencing a stored GCS document.

        Args:
            doc_id: GCS document identifier.

        Returns:
            Input instance with mode="doc_id".
        """
        return cls(mode="doc_id", doc_id=doc_id)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> "Input":
        """Reconstruct an Input from a dictionary, handling nested InputFile objects.

        Args:
            data: Dictionary (e.g. from Firestore or to_dict()).

        Returns:
            Input instance with InputFile objects in files list.
        """
        files_raw = data.get("files", [])
        files = [
            InputFile.from_dict(f) if isinstance(f, dict) else f
            for f in files_raw
        ]
        return cls(
            mode=data.get("mode", ""),
            text=data.get("text"),
            doc_id=data.get("doc_id"),
            files=files,
        )
