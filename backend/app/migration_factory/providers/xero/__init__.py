from ...domain import ProviderKey
from ..base import ReadOnlySkeletonAdapter


class XeroAdapter(ReadOnlySkeletonAdapter):
    provider = ProviderKey("xero")
