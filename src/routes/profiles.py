from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db, ActivationTokenModel, UserGroupEnum
from database.models.accounts import UserModel, UserProfileModel
from exceptions import TokenExpiredError, InvalidTokenError
from schemas.profiles import ProfileCreateSchema, ProfileResponseSchema
from schemas.accounts import UserActivationRequestSchema, MessageResponseSchema
from security.token_manager import JWTAuthManager
from storages.interfaces import S3StorageInterface
from config.dependencies import get_s3_storage_client, get_accounts_email_notificator
from validation.profile import validate_image
from notifications.interfaces import EmailSenderInterface
from fastapi.security import OAuth2PasswordBearer
import os

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/accounts/login/")

token_manager = JWTAuthManager(
    secret_key_access=os.getenv("SECRET_KEY_ACCESS", "default_access_secret"),
    secret_key_refresh=os.getenv("SECRET_KEY_REFRESH", "default_refresh_secret"),
    algorithm=os.getenv("JWT_SIGNING_ALGORITHM", "HS256"),
)

async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db),
) -> UserModel:
    try:
        payload = token_manager.decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject"
            )

        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await db.execute(stmt)
        user = result.scalars().first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return user

    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired."
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token."
        )


@router.post("/users/{user_id}/profile/",
             response_model=ProfileResponseSchema,
             status_code=status.HTTP_201_CREATED
             )
async def create_user_profile(
        user_id: int,
        profile_data: ProfileCreateSchema = Depends(),
        avatar: UploadFile | None = None,
        db: AsyncSession = Depends(get_db),
        current_user: UserModel = Depends(get_current_user),
        s3_client: S3StorageInterface = Depends(get_s3_storage_client),
):
    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or not active."
        )

    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this profile."
        )

    stmt = select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    result = await db.execute(stmt)
    existing_profile = result.scalars().first()
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile already exists."
        )

    avatar_url = None
    if avatar:
        validate_image(avatar)
        avatar_key = f"avatars/{user_id}_avatar.jpg"
        try:
            await s3_client.upload_fileobj(avatar.file, avatar_key)
            avatar_url = await s3_client.get_file_url(avatar_key)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload avatar. Please try again later."
            )


    new_profile = UserProfileModel(
        user_id=user_id,
        first_name=profile_data.first_name,
        last_name=profile_data.last_name,
        gender=profile_data.gender,
        date_of_birth=profile_data.date_of_birth,
        info=profile_data.info,
        avatar=avatar_url,
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    return new_profile
