from typing import Annotated

from fastapi import Depends, Request

from app.api.dependencies import ConsumerAuth, DatabaseSession, UserPrincipal, get_request_settings, get_resources
from app.core.request_metadata import request_metadata
from app.domains.assets.schemas import UploaderType
from app.services.account_security import ConsumerAccountService
from app.services.accounts import UserProfileService
from app.services.assets import AssetUploader
from app.services.consumer_phone import ConsumerPhoneService


def consumer_phone(auth: ConsumerAuth) -> ConsumerPhoneService:
    return ConsumerPhoneService(auth)


ConsumerPhone = Annotated[ConsumerPhoneService, Depends(consumer_phone)]


def consumer_profile(request: Request, session: DatabaseSession) -> UserProfileService:
    return UserProfileService(session=session, settings=get_request_settings(request))


def consumer_avatar_uploader(current: UserPrincipal) -> AssetUploader:
    return AssetUploader(type=UploaderType.USER, id=current.user.id)


def consumer_account(request: Request, session: DatabaseSession) -> ConsumerAccountService:
    return ConsumerAccountService(
        session=session,
        session_factory=get_resources(request).session_factory,
        metadata=request_metadata(request),
    )


ConsumerProfile = Annotated[UserProfileService, Depends(consumer_profile)]
ConsumerAvatarUploader = Annotated[AssetUploader, Depends(consumer_avatar_uploader)]
ConsumerAccount = Annotated[ConsumerAccountService, Depends(consumer_account)]
