"""Token counting with one tokenizer for generation and window accounting (PLAN §5).

Provider-reported token counts differ (chat formatting adds a few tokens per message); the
harness logs those separately.
"""

from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache

import tiktoken


@lru_cache(maxsize=4)
def encoding(name: str = "o200k_base") -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


def count(text: str, name: str = "o200k_base") -> int:
    return len(encoding(name).encode(text, disallowed_special=()))


def encode(text: str, name: str = "o200k_base") -> list[int]:
    return encoding(name).encode(text, disallowed_special=())


def decode(tokens: list[int], name: str = "o200k_base") -> str:
    return encoding(name).decode(tokens)


def token_offset(text: str, char_index: int, name: str = "o200k_base") -> int:
    """Number of tokens in text[:char_index] (the token offset of a character position)."""
    return count(text[:char_index], name)


class TokenIndex:
    """Token positions of character offsets in one encoded text (one encode, many lookups).

    `token_at(i)` is the index of the token that contains character i of the full text's
    encoding, which can differ by a token from `token_offset` where BPE merges across i."""

    def __init__(self, text: str, name: str = "o200k_base"):
        enc = encoding(name)
        toks = enc.encode(text, disallowed_special=())
        decoded, self.starts = enc.decode_with_offsets(toks)
        if decoded != text:
            raise ValueError("text does not round-trip through the tokenizer")
        self.n_tokens = len(toks)

    def token_at(self, char_index: int) -> int:
        return bisect_right(self.starts, char_index) - 1
