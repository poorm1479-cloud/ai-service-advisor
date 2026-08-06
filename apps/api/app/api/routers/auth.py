from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import CurrentUser, get_current_user, get_uow
from app.api.schemas import (
    AdminLoginRequest,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    RegisterShopRequest,
    SendOtpRequest,
    SendOtpResponse,
    TokenResponse,
    VerifyOtpRequest,
    VerifyOtpResponse,
)
from app.application.services import AuthService
from app.auth.otp import AuthOtpService, normalize_email, normalize_phone
from app.domain.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.saas.password_reset import PasswordResetService
from app.saas.rate_limit import admin_login_lockout, auth_rate_limiter, client_key

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class PasswordResetRequestBody(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=8, max_length=32)


class PasswordResetConfirmBody(BaseModel):
    token: str = Field(min_length=20)
    new_password: str = Field(min_length=8, max_length=128)


def _to_token_response(tokens) -> TokenResponse:
    role = tokens.role
    role_value = role.value if hasattr(role, "value") else str(role)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        user_id=tokens.user_id,
        shop_id=tokens.shop_id,
        role=role_value,
        capabilities=list(getattr(tokens, "capabilities", []) or []),
        primary_auth_method=getattr(tokens, "primary_auth_method", "phone"),
        username=getattr(tokens, "username", None),
        phone=tokens.phone,
        email=tokens.email,
        full_name=tokens.full_name,
        shop_name=tokens.shop_name or "",
        shop_slug=tokens.shop_slug or "",
        account_type=getattr(tokens, "account_type", "shop") or "shop",
        mfa_required=bool(getattr(tokens, "mfa_required", False)),
        mfa_token=getattr(tokens, "mfa_token", None),
    )


@router.post("/otp/send", response_model=SendOtpResponse)
async def send_otp(body: SendOtpRequest, request: Request) -> SendOtpResponse:
    auth_rate_limiter.check(client_key(request, "otp"))
    service = AuthOtpService()
    try:
        result = await service.send_otp(
            channel=body.channel,  # type: ignore[arg-type]
            phone=body.phone,
            email=str(body.email) if body.email else None,
            purpose=body.purpose,  # type: ignore[arg-type]
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    return SendOtpResponse(
        channel=result.channel,
        target=result.target,
        purpose=result.purpose,
        expires_in=result.expires_in,
        resend_after=result.resend_after,
        challenge_id=str(result.challenge_id),
        phone=result.phone,
        email=result.email,
        dev_code=result.dev_code,
        message=(
            "Verification code sent by SMS"
            if result.channel == "phone"
            else "Verification code sent by email"
        ),
    )


@router.post("/otp/verify", response_model=VerifyOtpResponse)
async def verify_otp(body: VerifyOtpRequest) -> VerifyOtpResponse:
    service = AuthOtpService()
    try:
        await service.verify_otp(
            channel=body.channel,  # type: ignore[arg-type]
            phone=body.phone,
            email=str(body.email) if body.email else None,
            code=body.code,
            purpose=body.purpose,  # type: ignore[arg-type]
            consume=False,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    target = (
        normalize_phone(body.phone or "")
        if body.channel == "phone"
        else normalize_email(str(body.email or ""))
    )
    return VerifyOtpResponse(ok=True, channel=body.channel, target=target, purpose=body.purpose)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@router.post(
    "/register-shop",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def register(body: RegisterShopRequest, uow: SqlAlchemyUnitOfWork = Depends(get_uow)) -> TokenResponse:
    service = AuthService(uow)
    try:
        tokens = await service.register_shop(
            shop_name=body.shop_name,
            shop_slug=body.shop_slug,
            auth_method=body.auth_method,
            owner_full_name=body.owner_full_name,
            password=body.password,
            owner_phone=body.owner_phone,
            owner_email=str(body.owner_email) if body.owner_email else None,
            timezone=body.timezone,
        )
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _to_token_response(tokens)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, uow: SqlAlchemyUnitOfWork = Depends(get_uow)) -> TokenResponse:
    auth_rate_limiter.check(client_key(request, "login"))
    service = AuthService(uow)
    try:
        tokens = await service.login(
            password=body.password,
            shop_name=body.shop_name,
            shop_slug=body.shop_slug,
            phone=body.phone,
            email=str(body.email) if body.email else None,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _to_token_response(tokens)


@router.post("/admin/login", response_model=TokenResponse)
async def admin_login(
    body: AdminLoginRequest, request: Request, uow: SqlAlchemyUnitOfWork = Depends(get_uow)
) -> TokenResponse:
    auth_rate_limiter.check(client_key(request, "admin_login"))
    lock_key = client_key(request, f"admin_fail:{(body.username or '').strip().lower()}")
    admin_login_lockout.assert_not_locked(lock_key)
    service = AuthService(uow)
    try:
        tokens = await service.login_platform_admin(
            username=body.username,
            password=body.password,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AuthenticationError as exc:
        detail, retry_after = admin_login_lockout.record_failure(lock_key)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
                headers={"Retry-After": str(retry_after)},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        ) from exc
    admin_login_lockout.clear(lock_key)
    return _to_token_response(tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, uow: SqlAlchemyUnitOfWork = Depends(get_uow)) -> TokenResponse:
    service = AuthService(uow)
    try:
        tokens = await service.refresh(raw_refresh_token=body.refresh_token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _to_token_response(tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest, uow: SqlAlchemyUnitOfWork = Depends(get_uow)) -> None:
    service = AuthService(uow)
    await service.logout(raw_refresh_token=body.refresh_token)


@router.get("/me", response_model=MeResponse)
async def me(
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> MeResponse:
    if current.shop_id is None or current.role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shop profile unavailable for platform admin",
        )
    service = AuthService(uow)
    try:
        result = await service.me(
            user_id=current.user_id,
            shop_id=current.shop_id,
            role=current.role,
            capabilities=list(current.capabilities),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MeResponse(
        user_id=result.user_id,
        primary_auth_method=result.primary_auth_method,
        username=result.username,
        phone=result.phone,
        email=result.email,
        full_name=result.full_name,
        shop_id=result.shop_id,
        shop_name=result.shop_name,
        shop_slug=result.shop_slug,
        role=result.role,
        capabilities=list(result.capabilities),
        phone_verified=result.phone_verified,
        email_verified=result.email_verified,
        mfa_enabled=result.mfa_enabled,
    )


class MfaVerifyBody(BaseModel):
    mfa_token: str = Field(min_length=20)
    code: str = Field(min_length=6, max_length=8)


class MfaConfirmBody(BaseModel):
    code: str = Field(min_length=6, max_length=8)


@router.post("/mfa/verify", response_model=TokenResponse)
async def mfa_verify(
    body: MfaVerifyBody,
    request: Request,
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> TokenResponse:
    auth_rate_limiter.check(client_key(request, "mfa"))
    service = AuthService(uow)
    try:
        tokens = await service.complete_mfa(mfa_token=body.mfa_token, code=body.code)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _to_token_response(tokens)


@router.post("/mfa/setup/begin")
async def mfa_setup_begin(
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> dict:
    try:
        return await AuthService(uow).begin_mfa_setup(user_id=current.user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/mfa/setup/confirm")
async def mfa_setup_confirm(
    body: MfaConfirmBody,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> dict:
    try:
        return await AuthService(uow).confirm_mfa_setup(user_id=current.user_id, code=body.code)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/mfa/backup-codes/regenerate")
async def mfa_regenerate_backup_codes(
    body: MfaConfirmBody,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> dict:
    try:
        return await AuthService(uow).regenerate_mfa_backup_codes(
            user_id=current.user_id, code=body.code
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/mfa/disable")
async def mfa_disable(
    body: MfaConfirmBody,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> dict:
    try:
        return await AuthService(uow).disable_mfa(user_id=current.user_id, code=body.code)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/password-reset/request")
async def password_reset_request(body: PasswordResetRequestBody, request: Request) -> dict:
    auth_rate_limiter.check(client_key(request, "password-reset"))
    try:
        return await PasswordResetService().request_reset(
            email=str(body.email) if body.email else None,
            phone=body.phone,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/password-reset/confirm")
async def password_reset_confirm(body: PasswordResetConfirmBody, request: Request) -> dict:
    auth_rate_limiter.check(client_key(request, "password-reset-confirm"))
    try:
        await PasswordResetService().reset_password(token=body.token, new_password=body.new_password)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True}
