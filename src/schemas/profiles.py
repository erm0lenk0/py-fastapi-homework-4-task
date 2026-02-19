from datetime import date
from fastapi import UploadFile, Form, File, HTTPException
from pydantic import BaseModel, field_validator, HttpUrl

from validation.profile import (
    validate_name,
    validate_image,
    validate_gender,
    validate_birth_date
)

class ProfileCreateSchema(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: UploadFile | None = None

    @field_validator("first_name")
    def validate_first_name(cls, v):
        validate_name(v)
        return v

    @field_validator("last_name")
    def validate_last_name(cls, v):
        validate_name(v)
        return v

    @field_validator("gender")
    def validate_gender_field(cls, v):
        validate_gender(v)
        return v


    @field_validator("date_of_birth")
    def validate_birth_date_field(cls, v):
        validate_birth_date(v)
        return v

    @field_validator("info")
    def validate_info_field(cls, v):
        if not v.strip():
            raise ValueError("Info must not be empty or whitespace")

    @field_validator("avatar")
    def validate_avatar(cls, v):
        if v:
            validate_image(v)
        return v

class ProfileResponseSchema(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: HttpUrl | None

    class Config:
        orm_mode = True