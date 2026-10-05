"""MFA (TOTP) commands and handlers.

The setup/verify-setup flow stashes a pending secret on the user row,
verifies the first code, then atomically flips ``mfa_enabled=True`` and
returns a one-time view of eight backup codes. ``mfa/verify`` (called
with the step-up token from ``verify-phone``) accepts either a TOTP code
or an unused backup code and issues a full token pair.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.auth import TokenPair, _format_user, build_tokens
from application.errors import ServiceError
from domain.errors import UserDeactivatedError, UserNotFoundError
from infrastructure.auth_stepup import (
    MfaSetupTokenError,
    MfaStepUpTokenError,
    build_mfa_setup_token,
    decode_mfa_setup_token,
    decode_mfa_token,
    issue_mfa_token,
)
from infrastructure.messaging import auth_events
from infrastructure.repositories import auth_repository as repo
from infrastructure.services.totp import (
    build_otpauth_url,
    generate_backup_codes,
    generate_secret,
    hash_backup_code,
    render_qr_png_base64,
    verify_code,
)

logger = logging.getLogger("carcraft-backend")

_ISSUER = "Carcraft"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass
class SetupMfaCommand:
    user_id: UUID


@dataclass
class VerifyMfaSetupCommand:
    user_id: UUID
    code: str


@dataclass
class VerifyMfaLoginCommand:
    mfa_token: str
    code: str


@dataclass
class DisableMfaCommand:
    user_id: UUID
    code: str


@dataclass
class InitMfaSetupCommand:
    """Mandatory-enrolment QR step: exchange the setup token for a QR.

    The caller has a ``setup_token`` from ``verify-phone`` but no access
    token yet — so the normal ``/mfa/setup`` endpoint (which requires full
    auth) isn't reachable. This command stashes a pending secret using
    only the setup token's identity and returns the otpauth URL + QR.
    """

    setup_token: str


@dataclass
class RegenerateBackupCodesCommand:
    """Regenerate backup codes for an enrolled user.

    Invalidates the previous set — caller is expected to surface the new
    codes to the user exactly once.
    """

    user_id: UUID


@dataclass
class GetMfaStatusQuery:
    """Read-only MFA state projection for the status endpoint."""

    user_id: UUID


@dataclass
class CompleteMfaSetupCommand:
    """Mandatory-enrolment flow: user submits a setup token + first TOTP code.

    Distinct from :class:`VerifyMfaSetupCommand` — that one assumes the
    user is already logged in (access token), whereas this command runs
    in the half-session between phone verification and full login for
    privileged roles that haven't enrolled yet.
    """

    setup_token: str
    code: str


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class MfaSetupResult:
    secret: str
    otpauth_url: str
    qr_png_base64: str


@dataclass
class MfaActivationResult:
    backup_codes: list[str]


@dataclass
class MfaLoginResult:
    user: dict
    tokens: TokenPair


@dataclass
class MfaStepUpRequired:
    """Marker returned from ``handle_verify_phone`` when 2FA is needed."""

    mfa_token: str
    user_id: UUID


@dataclass
class MfaSetupRequired:
    """Marker returned from ``handle_verify_phone`` when the user's role
    requires MFA but enrolment hasn't happened yet — the client should
    call ``POST /auth/mfa/complete-setup`` with this token.
    """

    setup_token: str
    user_id: UUID


@dataclass
class MfaCompleteSetupResult:
    """Full-login payload after a successful mandatory-setup enrolment."""

    user: dict
    tokens: TokenPair
    backup_codes: list[str]


@dataclass
class MfaStatusResult:
    """Projection returned by ``GET /auth/mfa``.

    ``backup_codes_remaining`` is how many unused codes the user still
    holds — useful in the settings UI to prompt regeneration once they've
    burned most of the set. ``None`` when MFA isn't enabled.
    """

    enabled: bool
    method: str | None
    has_backup_codes: bool
    backup_codes_remaining: int | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _label_for(user: dict) -> str:
    """Prefer email for the authenticator label; fall back to phone."""
    return str(user.get("email") or user.get("phone") or f"user:{user['id']}")


def build_mfa_step_up(user_id: UUID) -> MfaStepUpRequired:
    """Issue a step-up token to be returned from verify-phone when MFA is on."""
    return MfaStepUpRequired(mfa_token=issue_mfa_token(user_id), user_id=user_id)


def build_mfa_setup_required(user_id: UUID) -> MfaSetupRequired:
    """Issue a setup token for privileged roles lacking MFA enrolment."""
    return MfaSetupRequired(
        setup_token=build_mfa_setup_token(user_id), user_id=user_id
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_setup_mfa(
    cmd: SetupMfaCommand,
    session: AsyncSession,
) -> MfaSetupResult:
    user = await repo.find_user_by_id(session, cmd.user_id)
    if user is None:
        raise UserNotFoundError()
    state = await repo.get_mfa_state(session, cmd.user_id)
    if state is not None and state["enabled"]:
        raise ServiceError("MFA уже включена", 409)

    secret = generate_secret()
    await repo.set_pending_mfa_secret(session, cmd.user_id, secret)

    otpauth_url = build_otpauth_url(secret, _label_for(dict(user)), _ISSUER)
    qr_png_base64 = render_qr_png_base64(otpauth_url)
    auth_events.emit(
        auth_events.MFA_SETUP_STARTED,
        user_id=cmd.user_id,
    )
    return MfaSetupResult(
        secret=secret,
        otpauth_url=otpauth_url,
        qr_png_base64=qr_png_base64,
    )


async def handle_verify_mfa_setup(
    cmd: VerifyMfaSetupCommand,
    session: AsyncSession,
) -> MfaActivationResult:
    state = await repo.get_mfa_state(session, cmd.user_id)
    if state is None:
        raise UserNotFoundError()
    if state["enabled"]:
        raise ServiceError("MFA уже включена", 409)
    pending = state["pending_secret"]
    if not pending:
        raise ServiceError("MFA setup не начат", 400)

    if not verify_code(pending, cmd.code):
        auth_events.emit(
            auth_events.MFA_LOGIN_FAILED,
            user_id=cmd.user_id,
            stage="setup",
            reason="invalid_code",
        )
        raise ServiceError("MFA_INVALID_CODE", 401)

    backup_pairs = generate_backup_codes()
    plain_codes = [plain for plain, _ in backup_pairs]
    hashes = [h for _, h in backup_pairs]
    await repo.activate_mfa(session, cmd.user_id, pending, hashes)

    auth_events.emit(auth_events.MFA_ENABLED, user_id=cmd.user_id)
    return MfaActivationResult(backup_codes=plain_codes)


async def handle_verify_mfa_login(
    cmd: VerifyMfaLoginCommand,
    session: AsyncSession,
) -> MfaLoginResult:
    try:
        payload = decode_mfa_token(cmd.mfa_token)
    except MfaStepUpTokenError as exc:
        raise ServiceError(exc.code, 401) from exc
    user_id = payload["user_id"]

    user = await repo.find_user_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError()
    if not user["is_active"]:
        raise UserDeactivatedError()

    state = await repo.get_mfa_state(session, user_id)
    if state is None or not state["enabled"] or not state["secret"]:
        raise ServiceError("MFA не настроена", 400)

    used_backup = False
    if verify_code(state["secret"], cmd.code):
        pass
    else:
        code_hash = hash_backup_code(cmd.code)
        if await repo.consume_backup_code(session, user_id, code_hash):
            used_backup = True
            auth_events.emit(
                auth_events.MFA_BACKUP_CODE_USED,
                user_id=user_id,
            )
        else:
            auth_events.emit(
                auth_events.MFA_LOGIN_FAILED,
                user_id=user_id,
                stage="login",
                reason="invalid_code",
            )
            raise ServiceError("MFA_INVALID_CODE", 401)

    tokens = await build_tokens(user, session)
    auth_events.emit(
        auth_events.MFA_LOGIN_SUCCEEDED,
        user_id=user_id,
        used_backup=used_backup,
    )
    return MfaLoginResult(user=_format_user(user), tokens=tokens)


async def handle_init_mfa_setup(
    cmd: InitMfaSetupCommand,
    session: AsyncSession,
) -> MfaSetupResult:
    """Exchange a setup token for a QR without requiring a full session.

    Mirrors :func:`handle_setup_mfa` but authenticates via setup token
    instead of ``get_current_user``. Needed so the frontend's mandatory-
    enrolment flow can fetch the QR between phone verification and the
    first full login.
    """
    try:
        payload = decode_mfa_setup_token(cmd.setup_token)
    except MfaSetupTokenError as exc:
        raise ServiceError(exc.code, 401) from exc
    user_id = payload["user_id"]

    user = await repo.find_user_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError()
    if not user["is_active"]:
        raise UserDeactivatedError()

    state = await repo.get_mfa_state(session, user_id)
    if state is not None and state["enabled"]:
        raise ServiceError("MFA уже включена", 409)

    secret = generate_secret()
    await repo.set_pending_mfa_secret(session, user_id, secret)

    otpauth_url = build_otpauth_url(secret, _label_for(dict(user)), _ISSUER)
    qr_png_base64 = render_qr_png_base64(otpauth_url)
    auth_events.emit(
        auth_events.MFA_SETUP_STARTED,
        user_id=user_id,
        via="mandatory_setup",
    )
    return MfaSetupResult(
        secret=secret,
        otpauth_url=otpauth_url,
        qr_png_base64=qr_png_base64,
    )


async def handle_complete_mfa_setup(
    cmd: CompleteMfaSetupCommand,
    session: AsyncSession,
) -> MfaCompleteSetupResult:
    """Mandatory-setup flow: exchange a setup token + TOTP code for a full session.

    Rejects with 409 if the user somehow already enabled MFA between the
    half-session issuance and this call (concurrent admin intervention,
    or a double-submit of the same setup token after success).
    """
    try:
        payload = decode_mfa_setup_token(cmd.setup_token)
    except MfaSetupTokenError as exc:
        raise ServiceError(exc.code, 401) from exc
    user_id = payload["user_id"]

    user = await repo.find_user_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError()
    if not user["is_active"]:
        raise UserDeactivatedError()

    state = await repo.get_mfa_state(session, user_id)
    if state is not None and state["enabled"]:
        raise ServiceError("MFA уже включена", 409)

    pending = state["pending_secret"] if state else None
    if not pending:
        # Half-session lost the pending secret: either the user never hit
        # /mfa/setup, or the pending was cleared. Tell the client to
        # restart enrolment rather than silently generating a new one here.
        raise ServiceError("MFA setup не начат", 400)

    if not verify_code(pending, cmd.code):
        auth_events.emit(
            auth_events.MFA_LOGIN_FAILED,
            user_id=user_id,
            stage="mandatory_setup",
            reason="invalid_code",
        )
        raise ServiceError("MFA_INVALID_CODE", 401)

    backup_pairs = generate_backup_codes()
    plain_codes = [plain for plain, _ in backup_pairs]
    hashes = [h for _, h in backup_pairs]
    await repo.activate_mfa(session, user_id, pending, hashes)

    tokens = await build_tokens(user, session)
    auth_events.emit(auth_events.MFA_ENABLED, user_id=user_id)
    auth_events.emit(
        auth_events.MFA_LOGIN_SUCCEEDED,
        user_id=user_id,
        via="mandatory_setup",
    )
    return MfaCompleteSetupResult(
        user=_format_user(user),
        tokens=tokens,
        backup_codes=plain_codes,
    )


async def handle_get_mfa_status(
    query: GetMfaStatusQuery,
    session: AsyncSession,
) -> MfaStatusResult:
    """Read current MFA config for an authenticated user.

    Returns ``enabled=False`` with ``method=None`` when the user has no
    enrolment yet. ``method`` is always ``"totp"`` while enabled —
    emitted explicitly for forward-compatibility if WebAuthn is added.
    """
    state = await repo.get_mfa_state(session, query.user_id)
    if state is None:
        raise UserNotFoundError()
    if not state["enabled"]:
        return MfaStatusResult(
            enabled=False,
            method=None,
            has_backup_codes=False,
            backup_codes_remaining=None,
        )
    remaining = len(state["backup_code_hashes"] or [])
    return MfaStatusResult(
        enabled=True,
        method="totp",
        has_backup_codes=remaining > 0,
        backup_codes_remaining=remaining,
    )


async def handle_regenerate_backup_codes(
    cmd: RegenerateBackupCodesCommand,
    session: AsyncSession,
) -> MfaActivationResult:
    """Issue a fresh batch of backup codes, invalidating the previous set."""
    state = await repo.get_mfa_state(session, cmd.user_id)
    if state is None:
        raise UserNotFoundError()
    if not state["enabled"]:
        raise ServiceError("MFA не включена", 400)

    backup_pairs = generate_backup_codes()
    plain_codes = [plain for plain, _ in backup_pairs]
    hashes = [h for _, h in backup_pairs]
    await repo.replace_mfa_backup_codes(session, cmd.user_id, hashes)
    auth_events.emit(auth_events.MFA_BACKUP_CODES_REGENERATED, user_id=cmd.user_id)
    return MfaActivationResult(backup_codes=plain_codes)


async def handle_disable_mfa(
    cmd: DisableMfaCommand,
    session: AsyncSession,
) -> None:
    state = await repo.get_mfa_state(session, cmd.user_id)
    if state is None:
        raise UserNotFoundError()
    if not state["enabled"] or not state["secret"]:
        raise ServiceError("MFA не включена", 400)

    if not verify_code(state["secret"], cmd.code):
        auth_events.emit(
            auth_events.MFA_LOGIN_FAILED,
            user_id=cmd.user_id,
            stage="disable",
            reason="invalid_code",
        )
        raise ServiceError("MFA_INVALID_CODE", 401)

    await repo.disable_mfa(session, cmd.user_id)
    auth_events.emit(auth_events.MFA_DISABLED, user_id=cmd.user_id)
