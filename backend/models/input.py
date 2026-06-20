"""Input model capturing the source of a pipeline run request."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field

from .base import JsonModel

if TYPE_CHECKING:
    from werkzeug.datastructures import FileStorage


INPUT_VERSION = "1.0"


class InputFile(JsonModel):
    """Metadata about a single uploaded file.

    Stores only filename, content_type, and size_bytes — NOT raw bytes —
    to avoid bloating Firestore documents.
    """

    filename: str
    content_type: str
    size_bytes: int


class Input(JsonModel):
    """Describes the source input for a pipeline run.

    Attributes:
        mode:        One of "file", "text", or "doc_id".
        text:        The raw text content (when mode == "text").
        doc_id:      GCS document identifier (when mode == "doc_id").
        files:       List of file metadata objects (when mode == "file").
        dataset_group: Dataset group name for batch dataset inputs.
        dataset_input: Dataset input identifier for batch dataset inputs.
        selected_files: Dataset file names selected for batch dataset inputs.
        batch_group_id: Group-scoped identifier for a batch run.
    """

    mode: str  # "file" | "text" | "doc_id"
    text: str | None = None
    doc_id: str | None = None
    files: list[InputFile] = Field(default_factory=list)
    dataset_group: str | None = None
    dataset_input: str | None = None
    selected_files: list[str] | None = None
    batch_group_id: str | None = None

    # ------------------------------------------------------------------
    # Constructor helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_file_uploads(cls, uploads: list[Any]) -> "Input":
        """Create an Input from a list of werkzeug FileStorage objects.

        Reads each upload's stream to determine size_bytes, then resets the
        stream position with seek(0) so that downstream code (e.g. PDF-merge
        logic in care_plan.py) can still read the bytes.

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

    @classmethod
    def from_batch_dataset(
        cls,
        text: str,
        dataset_group: str,
        dataset_input: str,
        selected_files: list[str],
        batch_group_id: str,
    ) -> "Input":
        """Create an Input from concatenated preset dataset text."""
        return cls(
            mode="text",
            text=text,
            dataset_group=dataset_group,
            dataset_input=dataset_input,
            selected_files=selected_files,
            batch_group_id=batch_group_id,
        )
