from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from io import BytesIO

from config import get_jwt_auth_manager
from database import get_db
from database.models.accounts import UserModel, UserProfileModel
from exceptions import TokenExpiredError, InvalidTokenError
from schemas.profiles import ProfileCreateSchema, ProfileResponseSchema
from security.token_manager import JWTAuthManager
from storages.interfaces import S3StorageInterface
from config.dependencies import get_s3_storage_client
from validation.profile import validate_image, validate_gender, validate_birth_date, validate_name
from fastapi.security import OAuth2PasswordBearer


router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/accounts/login/")

async def get_token_from_header(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
        )
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'",
        )
    return auth_header.split(" ", 1)[1]

async def get_current_user(
        token: str = Depends(get_token_from_header),
        db: AsyncSession = Depends(get_db),
        jwt_manager: JWTAuthManager = Depends(get_jwt_auth_manager),
) -> UserModel:
    try:
        payload = jwt_manager.decode_access_token(token)
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user_id"
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
        profile_data: ProfileCreateSchema = Depends(ProfileCreateSchema.as_form),
        avatar: UploadFile | None = File(None),
        db: AsyncSession = Depends(get_db),
        current_user: UserModel = Depends(get_current_user),
        s3_client: S3StorageInterface = Depends(get_s3_storage_client),
):
    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active."
        )

    if current_user.id != user_id and current_user.group_id != 3:
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
            detail="User already has a profile."
        )

    try:
        validate_name(profile_data.first_name)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{profile_data.first_name} contains non-english letters."
        )

    try:
        validate_name(profile_data.last_name)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{profile_data.last_name} contains non-english letters."
        )


    try:
        validate_birth_date(profile_data.date_of_birth)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )

    try:
        validate_gender(profile_data.gender)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )

    if not profile_data.info.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Info field cannot be empty or contain only spaces."
        )

    avatar_url = None
    avatar_key = None
    if avatar:
        try:
            validate_image(avatar)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e)
            )

        avatar_key = f"avatars/{user_id}_avatar.jpg"
        try:
            content = await avatar.read()
            await s3_client.upload_file(avatar_key, content)
            avatar_url = await s3_client.get_file_url(avatar_key)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload avatar. Please try again later."
            )


    new_profile = UserProfileModel(
        user_id=user_id,
        first_name=profile_data.first_name.lower(),
        last_name=profile_data.last_name.lower(),
        gender=profile_data.gender,
        date_of_birth=profile_data.date_of_birth,
        info=profile_data.info,
        avatar=avatar_key,
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    response = ProfileResponseSchema(
        id=new_profile.id,
        user_id=new_profile.user_id,
        first_name=new_profile.first_name,
        last_name=new_profile.last_name,
        gender=new_profile.gender,
        date_of_birth=new_profile.date_of_birth,
        info=new_profile.info,
        avatar=avatar_url,
    )

    return response
