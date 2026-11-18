from ...domain import ProviderKey
from ..base import ReadOnlySkeletonAdapter


class HousecallProAdapter(ReadOnlySkeletonAdapter):
    provider = ProviderKey("housecall_pro")
