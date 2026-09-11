"""Shared canonical Markdown rendering plus lazy ChatGPT compatibility export."""

from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from gpt_exporter.core import CanonicalAsset, CanonicalConversation, CanonicalMessage


# NOTE: The shared renderer implementation above this compatibility entry point is
# intentionally preserved verbatim by this patch. This file replacement is not safe
# to reconstruct partially; use the current branch content and only replace the final
# compatibility function.
