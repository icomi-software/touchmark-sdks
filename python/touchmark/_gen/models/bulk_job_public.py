from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.bulk_job_public_kind import BulkJobPublicKind
from ..models.bulk_job_public_status import BulkJobPublicStatus

if TYPE_CHECKING:
    from ..models.webhook_state import WebhookState


T = TypeVar("T", bound="BulkJobPublic")


@_attrs_define
class BulkJobPublic:
    """
    Attributes:
        id (UUID):
        kind (BulkJobPublicKind):
        country (None | str): A phone job's default country for numbers written without +.
        status (BulkJobPublicStatus):
        filename (str):
        columns (list[str]):
        email_column (int | None):
        row_count (int):
        unique_count (int | None):
        credits_required (int | None):
        smtp_credits_required (int | None):
        smtp (bool):
        processed_rows (int):
        credits_reserved (int):
        credits_used (int):
        cancel_requested (bool):
        error (None | str):
        created_at (datetime.datetime):
        started_at (datetime.datetime | None):
        finished_at (datetime.datetime | None):
        expires_at (datetime.datetime):
        webhook_url (None | str):
        webhook (None | WebhookState):
    """

    id: UUID
    kind: BulkJobPublicKind
    country: None | str
    status: BulkJobPublicStatus
    filename: str
    columns: list[str]
    email_column: int | None
    row_count: int
    unique_count: int | None
    credits_required: int | None
    smtp_credits_required: int | None
    smtp: bool
    processed_rows: int
    credits_reserved: int
    credits_used: int
    cancel_requested: bool
    error: None | str
    created_at: datetime.datetime
    started_at: datetime.datetime | None
    finished_at: datetime.datetime | None
    expires_at: datetime.datetime
    webhook_url: None | str
    webhook: None | WebhookState
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.webhook_state import WebhookState  # noqa: PLC0415

        id = str(self.id)

        kind = self.kind.value

        country: None | str
        country = self.country

        status = self.status.value

        filename = self.filename

        columns = self.columns

        email_column: int | None
        email_column = self.email_column

        row_count = self.row_count

        unique_count: int | None
        unique_count = self.unique_count

        credits_required: int | None
        credits_required = self.credits_required

        smtp_credits_required: int | None
        smtp_credits_required = self.smtp_credits_required

        smtp = self.smtp

        processed_rows = self.processed_rows

        credits_reserved = self.credits_reserved

        credits_used = self.credits_used

        cancel_requested = self.cancel_requested

        error: None | str
        error = self.error

        created_at = self.created_at.isoformat()

        started_at: None | str
        if isinstance(self.started_at, datetime.datetime):
            started_at = self.started_at.isoformat()
        else:
            started_at = self.started_at

        finished_at: None | str
        if isinstance(self.finished_at, datetime.datetime):
            finished_at = self.finished_at.isoformat()
        else:
            finished_at = self.finished_at

        expires_at = self.expires_at.isoformat()

        webhook_url: None | str
        webhook_url = self.webhook_url

        webhook: dict[str, Any] | None
        if isinstance(self.webhook, WebhookState):
            webhook = self.webhook.to_dict()
        else:
            webhook = self.webhook

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "kind": kind,
                "country": country,
                "status": status,
                "filename": filename,
                "columns": columns,
                "email_column": email_column,
                "row_count": row_count,
                "unique_count": unique_count,
                "credits_required": credits_required,
                "smtp_credits_required": smtp_credits_required,
                "smtp": smtp,
                "processed_rows": processed_rows,
                "credits_reserved": credits_reserved,
                "credits_used": credits_used,
                "cancel_requested": cancel_requested,
                "error": error,
                "created_at": created_at,
                "started_at": started_at,
                "finished_at": finished_at,
                "expires_at": expires_at,
                "webhook_url": webhook_url,
                "webhook": webhook,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.webhook_state import WebhookState  # noqa: PLC0415

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        kind = BulkJobPublicKind(d.pop("kind"))

        def _parse_country(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        country = _parse_country(d.pop("country"))

        status = BulkJobPublicStatus(d.pop("status"))

        filename = d.pop("filename")

        columns = cast(list[str], d.pop("columns"))

        def _parse_email_column(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        email_column = _parse_email_column(d.pop("email_column"))

        row_count = d.pop("row_count")

        def _parse_unique_count(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        unique_count = _parse_unique_count(d.pop("unique_count"))

        def _parse_credits_required(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        credits_required = _parse_credits_required(d.pop("credits_required"))

        def _parse_smtp_credits_required(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        smtp_credits_required = _parse_smtp_credits_required(
            d.pop("smtp_credits_required")
        )

        smtp = d.pop("smtp")

        processed_rows = d.pop("processed_rows")

        credits_reserved = d.pop("credits_reserved")

        credits_used = d.pop("credits_used")

        cancel_requested = d.pop("cancel_requested")

        def _parse_error(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        error = _parse_error(d.pop("error"))

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        def _parse_started_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                started_at_type_0 = datetime.datetime.fromisoformat(data)

                return started_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        started_at = _parse_started_at(d.pop("started_at"))

        def _parse_finished_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                finished_at_type_0 = datetime.datetime.fromisoformat(data)

                return finished_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        finished_at = _parse_finished_at(d.pop("finished_at"))

        expires_at = datetime.datetime.fromisoformat(d.pop("expires_at"))

        def _parse_webhook_url(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        webhook_url = _parse_webhook_url(d.pop("webhook_url"))

        def _parse_webhook(data: object) -> None | WebhookState:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                webhook_type_0 = WebhookState.from_dict(data)

                return webhook_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | WebhookState, data)

        webhook = _parse_webhook(d.pop("webhook"))

        bulk_job_public = cls(
            id=id,
            kind=kind,
            country=country,
            status=status,
            filename=filename,
            columns=columns,
            email_column=email_column,
            row_count=row_count,
            unique_count=unique_count,
            credits_required=credits_required,
            smtp_credits_required=smtp_credits_required,
            smtp=smtp,
            processed_rows=processed_rows,
            credits_reserved=credits_reserved,
            credits_used=credits_used,
            cancel_requested=cancel_requested,
            error=error,
            created_at=created_at,
            started_at=started_at,
            finished_at=finished_at,
            expires_at=expires_at,
            webhook_url=webhook_url,
            webhook=webhook,
        )

        bulk_job_public.additional_properties = d
        return bulk_job_public

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
