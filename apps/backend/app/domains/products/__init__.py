"""商品领域公开接口。"""

from .schemas import (
    CategoryInput,
    CategoryRead,
    CategoryUpdate,
    ProductCreate,
    ProductRead,
    ProductStatusUpdate,
    ProductUpdate,
    SkuInput,
    SkuRead,
    SkuUpdate,
)
from .service import ProductService

__all__ = [
    "CategoryInput",
    "CategoryRead",
    "CategoryUpdate",
    "ProductCreate",
    "ProductRead",
    "ProductService",
    "ProductUpdate",
    "ProductStatusUpdate",
    "SkuInput",
    "SkuRead",
    "SkuUpdate",
]
