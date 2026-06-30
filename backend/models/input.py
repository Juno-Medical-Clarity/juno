"""Input model capturing the source of a pipeline run request."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal, Union

from pydantic import Field

from .base import JsonModel
from utils.constants import Constants

if TYPE_CHECKING:
    from werkzeug.datastructures import FileStorage


INPUT_VERSION = Constants.Schema.INPUT_VERSION


class InputFile(JsonModel):
    """Metadata about a single uploaded file.

    Stores only filename, content_type, and size_bytes — NOT raw bytes —
    to avoid bloating Firestore documents.
    """

    filename: str
    content_type: str
    size_bytes: int


class FileInput(JsonModel):
    mode: Literal["file"] = "file"
    files: list[InputFile] = Field(default_factory=list)
    pdf_gcs_url: str | None = None

    @classmethod
    def from_file_uploads(cls, uploads: list[Any]) -> "FileInput":
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
        return cls(files=input_files)


class TextInput(JsonModel):
    mode: Literal["text"] = "text"
    text: str | None = None


class DocIdInput(JsonModel):
    mode: Literal["doc_id"] = "doc_id"
    doc_id: str


class BatchDatasetInput(JsonModel):
    mode: Literal["batch_dataset"] = "batch_dataset"
    text: str
    dataset_group: str
    dataset_input: str
    selected_files: list[str]
    batch_group_id: str


Input = Annotated[
    Union[FileInput, TextInput, DocIdInput, BatchDatasetInput],
    Field(discriminator="mode"),
]


class ResolvedInput(JsonModel):
    """Structured representation of a resolved pipeline input.

    Built in route helpers before the pipeline is invoked; carries the extracted
    text, metadata about the source, and (for file inputs) the size in bytes of
    the merged PDF that was produced and uploaded to GCS.

    combined_pdf_size stores the byte count of the merged PDF as a float for
    observability. The raw bytes are uploaded to GCS by the caller before this
    object is constructed; this model never holds binary data directly.
    """

    text: str
    source_description: str
    source_filename: str
    combined_pdf_size: float | None = None
    source_kind: str = "upload"
    file_count: int = 0
    file_types: list[str] = Field(default_factory=list)
