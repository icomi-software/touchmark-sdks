from enum import StrEnum


class BulkJobPublicKind(StrEnum):
    EMAIL = "email"
    IP = "ip"
    PHONE = "phone"

    def __str__(self) -> str:
        return str(self.value)
