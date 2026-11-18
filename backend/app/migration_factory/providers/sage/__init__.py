from ...domain import ProviderKey
from ..base import ReadOnlySkeletonAdapter


class SageAdapter(ReadOnlySkeletonAdapter):
    provider = ProviderKey("sage")
