from datetime import date
from fastapi import Form
from pydantic import BaseModel, field_validator, HttpUrl
from pydantic_core import PydanticCustomError


from validation.profile import (
    validate_name,
    validate_gender,
    validate_birth_date
)

class ProfileCreateSchema(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str

    @classmethod
    def as_form(
            cls,
            first_name: str = Form(...),
            last_name: str = Form(...),
            gender: str = Form(...),
            date_of_birth: date = Form(...),
            info: str = Form(...),
    ):
        return cls(
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            date_of_birth=date_of_birth,
            info=info,
        )



class ProfileResponseSchema(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: HttpUrl | None

    model_config = {
        "from_attributes": True
    }