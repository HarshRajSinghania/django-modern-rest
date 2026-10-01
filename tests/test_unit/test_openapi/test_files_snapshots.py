import json
from typing import Annotated, ClassVar, Literal, TypeAlias

import pydantic
from django.http import FileResponse
from django.urls import path
from syrupy.assertion import SnapshotAssertion

from dmr import Body, Controller, FileMetadata, modify, validate
from dmr.files import FileResponseSpec
from dmr.negotiation import ContentType, conditional_type
from dmr.openapi import build_schema
from dmr.openapi.objects import Encoding, MediaTypeMetadata
from dmr.parsers import JsonParser, MultiPartParser
from dmr.plugins.pydantic import PydanticSerializer
from dmr.renderers import FileRenderer
from dmr.routing import Router
from dmr.settings import HttpSpec
from tests.infra.octet import OCTET_STREAM, OctetFileModel, OctetStreamParser


class _FileModel(pydantic.BaseModel):
    content_type: Literal['application/json', 'text/plain']
    size: int


class _SeveralFiles(pydantic.BaseModel):
    """Model docs."""

    __dmr_force_list__: ClassVar[frozenset[str]] = frozenset(('attachments',))

    attachments: list[_FileModel]
    second_file: _FileModel


class _FileController(Controller[PydanticSerializer]):
    parsers = (MultiPartParser(),)

    @modify(operation_id='file_test_id', deprecated=True)
    async def get(
        self,
        parsed_file_metadata: FileMetadata[_SeveralFiles],
    ) -> list[int]:
        raise NotImplementedError


def test_file_request_schema(snapshot: SnapshotAssertion) -> None:
    """Ensure that schema is correct for file controller."""
    assert (
        json.dumps(
            build_schema(
                Router(
                    '',
                    [path('file/', _FileController.as_view())],
                ),
            ).convert(),
            indent=2,
        )
        == snapshot
    )


class _OptionalFileModel(pydantic.BaseModel):
    content_type: Literal['text/plain']
    size: int


class _OtherFileModel(pydantic.BaseModel):
    content_type: Literal['image/png']
    size: int


class _OptionalFiles(pydantic.BaseModel):
    first_file: _OptionalFileModel
    second_file: _OptionalFileModel


class _MixedFiles(pydantic.BaseModel):
    first_file: _OtherFileModel
    second_file: _OptionalFileModel


class _OptionalFileController(Controller[PydanticSerializer]):
    parsers = (MultiPartParser(),)

    def post(
        self,
        parsed_file_metadata: FileMetadata[_OptionalFiles | None] = None,
    ) -> str:
        raise NotImplementedError


class _UnionFileController(Controller[PydanticSerializer]):
    parsers = (MultiPartParser(),)

    def post(
        self,
        parsed_file_metadata: FileMetadata[_OptionalFiles | _MixedFiles],
    ) -> str:
        raise NotImplementedError


def _multipart_encoding(
    controller: type[Controller[PydanticSerializer]],
) -> dict[str, object]:
    schema = build_schema(
        Router('', [path('file/', controller.as_view())]),
    ).convert()
    operation = schema['paths']['/file/']['post']
    request_body = operation['requestBody']['content']
    return request_body['multipart/form-data'].get('encoding')


def test_optional_file_metadata_keeps_encoding() -> None:
    """Optional FileMetadata still documents per-file content types."""
    assert _multipart_encoding(_OptionalFileController) == {
        'first_file': {'contentType': 'text/plain'},
        'second_file': {'contentType': 'text/plain'},
    }


def test_union_file_metadata_merges_encoding() -> None:
    """Unions of file models merge content types for a shared property."""
    assert _multipart_encoding(_UnionFileController) == {
        'first_file': {'contentType': 'text/plain, image/png'},
        'second_file': {'contentType': 'text/plain'},
    }
