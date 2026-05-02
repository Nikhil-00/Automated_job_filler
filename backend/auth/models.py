"""
backend/auth/models.py
───────────────────────
Pydantic request / response models for the auth routes.
"""
from __future__ import annotations

from pydantic import BaseModel


class SignupRequest(BaseModel):
    first_name: str
    last_name:  str
    email:      str
    phone:      str
    password:   str


class VerifyOtpRequest(BaseModel):
    email:    str
    otp_code: str


class LoginRequest(BaseModel):
    email:    str
    password: str


class ResendOtpRequest(BaseModel):
    email: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email:        str
    otp_code:     str
    new_password: str


class AuthResponse(BaseModel):
    token:       str
    user_id:     int
    first_name:  str
    last_name:   str
    email:       str
    role:        str
    has_profile: bool


class UserInfo(BaseModel):
    user_id:     int
    first_name:  str
    last_name:   str
    email:       str
    role:        str
    has_profile: bool
