from __future__ import annotations
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import (
    AuthError, register, login, confirm_email, resend_verify_code,
    send_reset_code, reset_password, verify_token, get_user,
)
from .config import settings

app = FastAPI(title="Messenger API")

# ---- Модели запросов ----

class RegisterIn(BaseModel):
    username: str
    email: str
    password: str

class LoginIn(BaseModel):
    login: str
    password: str

class VerifyIn(BaseModel):
    login: str
    code: str

class ResendIn(BaseModel):
    login: str

class RequestResetIn(BaseModel):
    email: str

class ResetIn(BaseModel):
    email: str
    code: str
    password: str

class TokenIn(BaseModel):
    token: str


# ---- Хелпер ----

def err(msg: str, status: int = 400):
    return JSONResponse({"ok": False, "error": msg}, status_code=status)


def ok(data: dict | None = None):
    return JSONResponse({"ok": True, **(data or {})})


# ---- Роуты ----

@app.post("/api/register")
async def api_register(body: RegisterIn):
    try:
        result = await register(body.username, body.email, body.password)
        return ok(result)
    except AuthError as e:
        return err(str(e))


@app.post("/api/login")
async def api_login(body: LoginIn):
    try:
        return ok(login(body.login, body.password))
    except AuthError as e:
        return err(str(e))


@app.post("/api/verify_email")
async def api_verify(body: VerifyIn):
    try:
        return ok(await confirm_email(body.login, body.code))
    except AuthError as e:
        return err(str(e))


@app.post("/api/resend_code")
async def api_resend(body: ResendIn):
    try:
        await resend_verify_code(body.login)
        return ok({"message": "Код отправлен повторно"})
    except AuthError as e:
        return err(str(e))


@app.post("/api/request_reset")
async def api_request_reset(body: RequestResetIn):
    try:
        await send_reset_code(body.email)
        return ok({"message": "Если email зарегистрирован, код отправлен"})
    except AuthError as e:
        return err(str(e))


@app.post("/api/reset_password")
async def api_reset(body: ResetIn):
    try:
        reset_password(body.email, body.code, body.password)
        return ok({"message": "Пароль обновлён"})
    except AuthError as e:
        return err(str(e))


@app.post("/api/me")
async def api_me(body: TokenIn):
    uid = verify_token(body.token)
    if not uid:
        return err("Неверный токен")
    user = get_user(uid)
    if not user:
        return err("Пользователь не найден")
    if not user["verified"]:
        return err("Email не подтверждён")
    return ok({"user": user})


# ---- Статика ----

@app.get("/")
async def index():
    return FileResponse(settings.WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=str(settings.WEB_DIR), html=True), name="static")