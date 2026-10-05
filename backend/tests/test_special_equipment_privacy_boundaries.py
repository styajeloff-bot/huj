from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from botocore.exceptions import ClientError

from application.tasks import special_equipment_import as import_tasks
from domain.special_equipment_import import ImportStatus
from infrastructure.services.object_storage import s3 as s3_module


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def commit(self) -> None:
        return None


class _LogSpy:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def error(self, message: str, *args: Any) -> None:
        self.messages.append(message % args)

    def warning(self, message: str, *args: Any) -> None:
        self.messages.append(message % args)


class _FailingImportStorage:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def download_to_path(self, _key: str, _path: Path) -> str:
        raise self._error


@pytest.mark.asyncio
async def test_import_validation_runtime_error_is_safe_for_logs_and_job_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()
    secret = "https://storage.internal/private?X-Amz-Signature=never-log"
    job = {
        "status": ImportStatus.UPLOADED.value,
        "lease_owner": None,
        "lease_until": None,
        "source_object_key": "private/source.xlsx",
    }
    captured: dict[str, Any] = {}
    log = _LogSpy()

    async def get_job(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return job

    async def update_job(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def mark_retryable(
        marked_job_id: UUID,
        code: str,
        detail: str,
    ) -> None:
        captured.update(job_id=marked_job_id, code=code, detail=detail)

    monkeypatch.setattr(import_tasks, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(import_tasks.repo, "get_job", get_job)
    monkeypatch.setattr(import_tasks.repo, "update_job", update_job)
    monkeypatch.setattr(import_tasks, "_mark_retryable", mark_retryable)
    monkeypatch.setattr(import_tasks, "logger", log)
    monkeypatch.setattr(
        import_tasks,
        "get_special_equipment_import_storage",
        lambda: _FailingImportStorage(RuntimeError(secret)),
    )

    await import_tasks.validate_special_equipment_import.original_func(str(job_id))

    assert captured == {
        "job_id": job_id,
        "code": "VALIDATION_RUNTIME_ERROR",
        "detail": import_tasks._VALIDATION_RUNTIME_ERROR_DETAIL,
    }
    assert secret not in "\n".join(log.messages)
    assert "error_type=RuntimeError" in log.messages[0]


@pytest.mark.asyncio
async def test_import_apply_runtime_error_is_safe_for_logs_and_job_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()
    secret = "s3://private-bucket/private/archive.zip?credential=never-log"
    job = {
        "status": ImportStatus.APPLYING.value,
        "normalized_artifact_key": "private/normalized.zip",
    }
    captured: dict[str, Any] = {}
    log = _LogSpy()

    async def get_job(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return job

    async def mark_failed(marked_job_id: UUID, code: str, detail: str) -> None:
        captured.update(job_id=marked_job_id, code=code, detail=detail)

    monkeypatch.setattr(import_tasks, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(import_tasks.repo, "get_job", get_job)
    monkeypatch.setattr(import_tasks, "_mark_failed", mark_failed)
    monkeypatch.setattr(import_tasks, "logger", log)
    monkeypatch.setattr(
        import_tasks,
        "get_special_equipment_import_storage",
        lambda: _FailingImportStorage(RuntimeError(secret)),
    )

    await import_tasks.apply_special_equipment_import.original_func(str(job_id))

    assert captured == {
        "job_id": job_id,
        "code": "APPLY_FAILED",
        "detail": import_tasks._APPLY_RUNTIME_ERROR_DETAIL,
    }
    assert secret not in "\n".join(log.messages)
    assert "error_type=RuntimeError" in log.messages[0]


class _FailingS3Client:
    def __init__(self, error: ClientError) -> None:
        self._error = error

    async def get_object(self, **_kwargs: Any) -> None:
        raise self._error

    async def delete_object(self, **_kwargs: Any) -> None:
        raise self._error

    async def head_object(self, **_kwargs: Any) -> None:
        raise self._error


class _S3ClientContext:
    def __init__(self, client: _FailingS3Client) -> None:
        self._client = client

    async def __aenter__(self) -> _FailingS3Client:
        return self._client

    async def __aexit__(self, *_args: Any) -> None:
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "expected_event"),
    (("get", "s3_get_failed"), ("delete", "s3_delete_failed"), ("exists", "s3_exists_failed")),
)
async def test_s3_failures_never_log_internal_object_keys(
    operation: str,
    expected_event: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_key = "special-equipment/private/customer-vin-never-log.pdf"
    error = ClientError(
        {
            "Error": {
                "Code": "InternalError",
                "Message": f"provider failed for {secret_key}",
            }
        },
        "GetObject",
    )
    client = _FailingS3Client(error)
    storage = s3_module.S3ObjectStorage(
        endpoint="https://storage.internal",
        region="test-1",
        bucket="private-bucket",
        access_key_id="access",
        secret_access_key="secret",
    )
    log = _LogSpy()
    monkeypatch.setattr(storage, "_client", lambda: _S3ClientContext(client))
    monkeypatch.setattr(s3_module, "logger", log)

    with pytest.raises(ClientError):
        await getattr(storage, operation)(secret_key)

    rendered = "\n".join(log.messages)
    assert expected_event in rendered
    assert "error_code=InternalError" in rendered
    assert secret_key not in rendered


def test_nginx_api_failure_diagnostics_are_query_free() -> None:
    config = (Path(__file__).parents[2] / "nginx.dev.conf").read_text(
        encoding="utf-8"
    )
    log_format = config.split("log_format carcraft", 1)[1].split(";", 1)[0]
    callback_location = config.split(
        "location = /api/v1/payments/webhook/modulkassa {", 1
    )[1].split("location /api {", 1)[0]
    api_location = config.split("location /api {", 1)[1].split(
        "location ^~ /.well-known/", 1
    )[0]

    assert "$request_method $uri $server_protocol" in log_format
    assert "$request_uri" not in log_format
    assert '"upstream_status":"$upstream_status"' in log_format
    assert '"upstream_connect_seconds":"$upstream_connect_time"' in log_format
    assert '"upstream_response_seconds":"$upstream_response_time"' in log_format
    assert "error_log /dev/null;" in callback_location
    assert "proxy_pass http://backend;" in callback_location
    assert "error_log /dev/null;" not in api_location
