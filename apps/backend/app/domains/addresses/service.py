from uuid import UUID

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.db.models.address import UserAddress

from .repository import AddressRepository
from .schemas import AddressInput, AddressRead, AddressUpdate


class AddressService:
    def __init__(self, repository: AddressRepository) -> None:
        self.repository = repository

    async def list_for_user(self, user_id: UUID) -> list[AddressRead]:
        rows = await self.repository.list_for_user(user_id)
        rows.sort(key=lambda row: not row.is_default)
        return [AddressRead.model_validate(row) for row in rows]

    async def snapshot(self, user_id: UUID, address_id: UUID) -> AddressRead:
        return AddressRead.model_validate(await self._get(user_id, address_id))

    async def _get(self, user_id: UUID, address_id: UUID) -> UserAddress:
        row = await self.repository.get(user_id, address_id)
        if row is None:
            raise AppException(status_code=404, code=ErrorCode.ADDRESS_NOT_FOUND, message="收货地址不存在")
        return row

    async def _clear_defaults(self, rows: list[UserAddress]) -> None:
        for row in rows:
            if row.is_default:
                row.is_default = False
                row.revision += 1
        await self.repository.flush()

    async def create(self, user_id: UUID, data: AddressInput) -> AddressRead:
        await self.repository.lock_owner(user_id)
        rows = await self.repository.list_for_user(user_id)
        if len(rows) >= 20:
            raise AppException(status_code=409, code=ErrorCode.ADDRESS_LIMIT, message="最多保存二十条收货地址")
        default = data.is_default or not rows
        if default:
            await self._clear_defaults(rows)
        row = UserAddress(user_id=user_id, **data.model_dump(exclude={"is_default"}), is_default=default, revision=1)
        await self.repository.save(row)
        return AddressRead.model_validate(row)

    async def update(self, user_id: UUID, address_id: UUID, data: AddressUpdate) -> AddressRead:
        await self.repository.lock_owner(user_id)
        row = await self._get(user_id, address_id)
        self._check_revision(row, data.revision)
        if data.is_default and not row.is_default:
            await self._clear_defaults(await self.repository.list_for_user(user_id))
        row.receiver_name = data.receiver_name
        row.mobile = data.mobile
        row.province_code = data.province_code
        row.city_code = data.city_code
        row.district_code = data.district_code
        row.province = data.province
        row.city = data.city
        row.district = data.district
        row.street_address = data.street_address
        row.is_default = data.is_default
        row.revision += 1
        await self.repository.save(row)
        return AddressRead.model_validate(row)

    async def delete(self, user_id: UUID, address_id: UUID, revision: int) -> None:
        await self.repository.lock_owner(user_id)
        row = await self._get(user_id, address_id)
        self._check_revision(row, revision)
        was_default = row.is_default
        await self.repository.delete(row)
        if was_default:
            rows = await self.repository.list_for_user(user_id)
            if rows:
                rows[0].is_default = True
                rows[0].revision += 1
                await self.repository.flush()

    @staticmethod
    def _check_revision(row: UserAddress, revision: int) -> None:
        if row.revision != revision:
            raise AppException(
                status_code=409, code=ErrorCode.ADDRESS_REVISION_CONFLICT, message="收货地址已变更，请重新读取"
            )
