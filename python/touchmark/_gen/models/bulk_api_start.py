from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="BulkApiStart")


@_attrs_define
class BulkApiStart:
    """
    Attributes:
        smtp (bool | Unset):  Default: False.
        smtp_limit (int | None | Unset):
        email_column (int | None | Unset):
        webhook_url (None | str | Unset):
    """

    smtp: bool | Unset = False
    smtp_limit: int | None | Unset = UNSET
    email_column: int | None | Unset = UNSET
    webhook_url: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        smtp = self.smtp

        smtp_limit: int | None | Unset
        if isinstance(self.smtp_limit, Unset):
            smtp_limit = UNSET
        else:
            smtp_limit = self.smtp_limit

        email_column: int | None | Unset
        if isinstance(self.email_column, Unset):
            email_column = UNSET
        else:
            email_column = self.email_column

        webhook_url: None | str | Unset
        if isinstance(self.webhook_url, Unset):
            webhook_url = UNSET
        else:
            webhook_url = self.webhook_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if smtp is not UNSET:
            field_dict["smtp"] = smtp
        if smtp_limit is not UNSET:
            field_dict["smtp_limit"] = smtp_limit
        if email_column is not UNSET:
            field_dict["email_column"] = email_column
        if webhook_url is not UNSET:
            field_dict["webhook_url"] = webhook_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        smtp = d.pop("smtp", UNSET)

        def _parse_smtp_limit(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        smtp_limit = _parse_smtp_limit(d.pop("smtp_limit", UNSET))

        def _parse_email_column(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        email_column = _parse_email_column(d.pop("email_column", UNSET))

        def _parse_webhook_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        webhook_url = _parse_webhook_url(d.pop("webhook_url", UNSET))

        bulk_api_start = cls(
            smtp=smtp,
            smtp_limit=smtp_limit,
            email_column=email_column,
            webhook_url=webhook_url,
        )

        bulk_api_start.additional_properties = d
        return bulk_api_start

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
