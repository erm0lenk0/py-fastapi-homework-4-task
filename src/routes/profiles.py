from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from config.settings import Settings

from database import get_db, ActivationTokenModel, UserGroupEnum
from database.models.accounts import UserModel, UserProfileModel
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
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

@router.post("/profiles/", response_model=ProfileResponseSchema)
async def create_profile(
    profile: ProfileCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    stmt = select(UserProfileModel).where(UserProfileModel.user_id == current_user.id)
    result = await db.execute(stmt)
    existing_profile = result.scalars().first()
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile already exists."
        )

    new_profile = UserProfileModel(
        user_id=current_user.id,
        first_name=profile.first_name,
        last_name=profile.last_name,
        gender=profile.gender,
        date_of_birth=profile.date_of_birth,
        info=profile.info,
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    return new_profile



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
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authenticated to create profile for another user."
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
        await s3_client.upload_fileobj(avatar.file, avatar_key)
        avatar_url = await s3_client.get_file_url(avatar_key)

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


@router.post(
    "/accounts/activate/",
    response_model=MessageResponseSchema,
    status_code=status.HTTP_200_OK,
)
async def activate_account(
        data: UserActivationRequestSchema,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db),
        email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
):
    stmt = (
        select(ActivationTokenModel)
        .join(UserModel)
        .where(UserModel.email == data.email, ActivationTokenModel.token == data.token)
    )
    result = await db.execute(stmt)
    activation_token = result.scalars().first()
    if not activation_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired activation token."
        )

    user = activation_token.user
    user.is_active = True
    await db.commit()

    background_tasks.add_task(
        email_sender.send_activation_complete_email,
        email=user.email,
        login_link="https://example.com/login",
    )

    return {"message": "User account activated successfully."}
