from fastapi import APIRouter, Depends, HTTPException, status
from poetry.core.packages.dependency import Dependency
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.testing.pickleable import User

from config.dependencies import get_s3_storage_client
from database.models.accounts import UserProfileModel
from schemas.profiles import ProfileCreate
from security.http import get_token
from storages.interfaces import S3StorageInterface
from storages.s3 import S3StorageClient
from database.session_postgresql import get_postgresql_db
from database.models.accounts import UserModel, UserProfileModel

router = APIRouter()

@router.post("/users/{user_id}/profile/", status_code=status.HTTP_201_CREATED)
async def create_profile(
        user_id: int,
        profile: ProfileCreate,
        db: AsyncSession = Depends(get_postgresql_db),
        token: str = Depends(get_token),
        s3_client: S3StorageInterface = Depends(get_s3_storage_client),
):
    user = await db.get(UserModel, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or not active.")

    if user.id != user_id and user.group.name == "USER":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to edit this profile.")

    existing_profile = await  db.get(UserProfileModel, {"user_id": user_id})
    if existing_profile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already has a profile.")

    try:
        avatar_url = await s3_client.upload_file(profile.avatar, f"{user_id}_avatar.jpg")
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to upload avatar. Please try again.")

    new_profile = UserProfileModel(
        first_name=profile.first_name,
        last_name=profile.last_name,
        gender=profile.gender,
        date_of_birth=profile.birth_date,
        info=profile.info,
        avatar=avatar_url,
        user_id=user_id,
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    return {
        "id": new_profile.id,
        "user_id": new_profile.user_id,
        "first_name": new_profile.first_name,
        "last_name": new_profile.last_name,
        "gender": new_profile.gender,
        "date_of_birth": str(new_profile.date_of_birth),
        "info": new_profile.info,
        "avatar": avatar_url,
    }