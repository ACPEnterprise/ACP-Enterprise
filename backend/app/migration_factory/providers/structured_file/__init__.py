from ...domain import ProviderKey
from ..base import ReadOnlySkeletonAdapter


class StructuredFileAdapter(ReadOnlySkeletonAdapter):
    provider = ProviderKey("structured_file")
