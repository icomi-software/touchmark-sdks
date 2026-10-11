from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from .. import types
from ..models.upload_bulk_file_body_kind import UploadBulkFileBodyKind
from ..types import UNSET, File, Unset

T = TypeVar("T", bound="UploadBulkFileBody")


@_attrs_define
class UploadBulkFileBody:
    """
    Attributes:
        file (File): A UTF-8 CSV file, at most 20 MB
        kind (UploadBulkFileBodyKind | Unset):  Default: UploadBulkFileBodyKind.EMAIL.
        country (str | Unset): Phone jobs: the ISO 3166-1 alpha-2 country of numbers written without +
    """

    file: File
    kind: UploadBulkFileBodyKind | Unset = UploadBulkFileBodyKind.EMAIL
    country: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        file = self.file.to_tuple()

        kind: str | Unset = UNSET
        if not isinstance(self.kind, Unset):
            kind = self.kind.value

        country = self.country

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "file": file,
            }
        )
        if kind is not UNSET:
            field_dict["kind"] = kind
        if country is not UNSET:
            field_dict["country"] = country

        return field_dict

    def to_multipart(self) -> types.RequestFiles:
        files: types.RequestFiles = []

        files.append(("file", self.file.to_tuple()))

        if not isinstance(self.kind, Unset):
            files.append(("kind", (None, str(self.kind.value).encode(), "text/plain")))

        if not isinstance(self.country, Unset):
            files.append(("country", (None, str(self.country).encode(), "text/plain")))

        for prop_name, prop in self.additional_properties.items():
            files.append((prop_name, (None, str(prop).encode(), "text/plain")))

        return files

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        file = File(payload=BytesIO(d.pop("file")))

        _kind = d.pop("kind", UNSET)
        kind: UploadBulkFileBodyKind | Unset
        if isinstance(_kind, Unset):
            kind = UNSET
        else:
            kind = UploadBulkFileBodyKind(_kind)

        country = d.pop("country", UNSET)

        upload_bulk_file_body = cls(
            file=file,
            kind=kind,
            country=country,
        )

        upload_bulk_file_body.additional_properties = d
        return upload_bulk_file_body

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
