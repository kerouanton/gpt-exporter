"""OpenAI ChatGPT provider implementation.

Everything in this package is provider-specific and may be removed without
invalidating the provider-neutral core architecture.
"""

from .provider import ChatGPTProvider

__all__ = ["ChatGPTProvider"]
