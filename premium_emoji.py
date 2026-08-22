"""
from premium_emoji import entities_for
Shared helper for sending Telegram Premium (custom) emoji inside bot messages.

Usage:
    from premium_emoji import entities_for

    text = "📦 Order ថ្មី #123"
    await update.message.reply_text(text, entities=entities_for(text))

How it works:
- emoji-map.json (emoji character -> premium custom_emoji_id) is loaded once at import.
- entities_for(text) scans the text for any emoji that's in the map and returns the
  list of MessageEntity(type=CUSTOM_EMOJI, ...) Telegram needs to render it as premium.
- The text itself is NOT modified - it still contains the normal emoji character as
  a fallback (for non-Premium viewers / old clients), exactly like Telegram's own apps do.
- Offsets/lengths are computed in UTF-16 code units (what the Bot API requires), not
  Python string length, so multi-codepoint emoji won't shift later entities.

IMPORTANT LIMITATION:
- Telegram does NOT support entities on InlineKeyboardButton labels. Button text
  (e.g. "✅ អនុម័ត") will always show the plain emoji - this only works for message text,
  captions, and similar rich-text fields.
- If a message uses parse_mode (Markdown/HTML), you CANNOT pass entities at the same
  time (Telegram API rejects that combo). For messages that need both premium emoji
  AND markdown formatting, the markdown must be converted to entities too, or dropped.
"""
import json
import os
from telegram import MessageEntity

# emoji-map.json lives at the project root, alongside config.py / main.py
_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emoji-map.json")

try:
    with open(_MAP_PATH, encoding="utf-8") as f:
        EMOJI_ID_MAP = json.load(f)
except FileNotFoundError:
    EMOJI_ID_MAP = {}

# Longest emoji first, so multi-codepoint sequences match before any shorter prefix would
_EMOJI_KEYS = sorted(EMOJI_ID_MAP.keys(), key=len, reverse=True)


def _utf16_len(s: str) -> int:
    """Length of s in UTF-16 code units (what Telegram entity offsets use)."""
    return len(s.encode("utf-16-le")) // 2


def entities_for(text: str):
    """Return a list of telegram.MessageEntity for every known premium emoji in text."""
    entities = []
    i = 0
    n = len(text)
    utf16_offset = 0
    while i < n:
        matched = None
        for emoji in _EMOJI_KEYS:
            L = len(emoji)
            if text[i:i + L] == emoji:
                matched = emoji
                break
        if matched:
            length_utf16 = _utf16_len(matched)
            entities.append(MessageEntity(
                type=MessageEntity.CUSTOM_EMOJI,
                offset=utf16_offset,
                length=length_utf16,
                custom_emoji_id=EMOJI_ID_MAP[matched],
            ))
            i += len(matched)
            utf16_offset += length_utf16
        else:
            utf16_offset += _utf16_len(text[i])
            i += 1
    return entities
