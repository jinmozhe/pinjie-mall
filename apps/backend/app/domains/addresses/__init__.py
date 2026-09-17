"""收货地址公开契约。"""

from .schemas import AddressInput, AddressRead, AddressUpdate
from .service import AddressService

__all__ = ["AddressInput", "AddressRead", "AddressService", "AddressUpdate"]
