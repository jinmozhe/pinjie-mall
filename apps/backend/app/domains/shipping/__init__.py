"""运费领域公开入口。"""

from .schemas import FreightQuote, ShippingTemplateInput, ShippingTemplateRead
from .service import ShippingService

__all__ = ["FreightQuote", "ShippingService", "ShippingTemplateInput", "ShippingTemplateRead"]
