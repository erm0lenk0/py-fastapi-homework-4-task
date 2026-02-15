from datetime import date

from fastapi import UploadFile, Form, File, HTTPException
from pydantic import BaseModel, field_validator, HttpUrl

from validation import (
    validate_name,
    validate_image,
    validate_gender,
    validate_birth_date
)

class ProfileCreate(BaseModel):
    first_name: str
    last_name: str
    gender: str
    birth_date: date
    info: str
    avatar: bytes

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


    @field_validator("birth_date")
    def validate_birth_date_field(cls, v):
        validate_birth_date(v)
        return v

    @field_validator("avatar")
    def validate_avatar(cls, v):
        validate_image(v)
        return v
