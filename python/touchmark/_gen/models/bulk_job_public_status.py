from enum import StrEnum


class BulkJobPublicStatus(StrEnum):
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    EXPIRED = "expired"
    FAILED = "failed"
    QUEUED = "queued"
    READY = "ready"
    RUNNING = "running"
    UPLOADED = "uploaded"

    def __str__(self) -> str:
        return str(self.value)
