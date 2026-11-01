"""Flashcards converter: transforms Gemini Notebook flashcards into JSON and Anki-compatible CSV.

Supports standard Anki import formatting (front, back, tags) with HTML/newlines
and RFC 4180 quote escaping.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

from notebooklm_batch_studio.domain.models import Flashcard

logger = logging.getLogger(__name__)


def _extract_card_text(field_val: Any) -> str:
    """Extract text from either a string or Gemini Notebook's nested block structure.

    Args:
        field_val: Raw field value from JSON, which may be a string or a dict
                   containing 'flashcardContentBlock'.

    Returns:
        Extracted plain text string.
    """
    if isinstance(field_val, str):
        return field_val.strip()
    if not isinstance(field_val, dict):
        return ""

    blocks = field_val.get("flashcardContentBlock", [])
    if not isinstance(blocks, list):
        return ""

    parts: list[str] = []
    for b in blocks:
        if isinstance(b, dict) and "content" in b:
            parts.append(str(b["content"]))
        elif isinstance(b, str):
            parts.append(b)
    return "\n".join(parts).strip()


def parse_notebooklm_flashcards(raw_data: dict[str, Any] | list[Any]) -> list[Flashcard]:
    """Parse raw Gemini Notebook flashcards JSON into a list of domain Flashcard entities.

    Args:
        raw_data: Raw JSON dictionary (with 'cards' key) or list of card objects.

    Returns:
        List of parsed domain Flashcard entities.
    """
    if isinstance(raw_data, dict):
        cards_raw = raw_data.get("cards", [])
    elif isinstance(raw_data, list):
        cards_raw = raw_data
    else:
        cards_raw = []

    cards: list[Flashcard] = []
    for c in cards_raw:
        if not isinstance(c, dict):
            continue
        front_text = _extract_card_text(c.get("front"))
        back_text = _extract_card_text(c.get("back"))
        source_text = str(c.get("source", "")).strip()

        if front_text and back_text:
            cards.append(Flashcard(front=front_text, back=back_text, source=source_text))

    logger.info("Parsed %d flashcards from raw input.", len(cards))
    return cards


def to_json(cards: list[Flashcard], title: str = "") -> str:
    """Serialize Flashcard entities into standard JSON.

    Args:
        cards: List of domain Flashcard entities.
        title: Optional title for the flashcard deck.

    Returns:
        JSON string representation.
    """
    payload = {
        "title": title or "Course Flashcards",
        "cards_count": len(cards),
        "cards": [
            {
                "front": card.front,
                "back": card.back,
                "source": card.source,
            }
            for card in cards
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def to_anki_csv(cards: list[Flashcard], tags: list[str] | None = None) -> str:
    """Export Flashcards to Anki-compatible CSV format.

    In Anki, multiple tags are separated by single spaces. The CSV columns are:
    Front, Back, Tags.

    Args:
        cards: List of domain Flashcard entities.
        tags: Optional list of tag strings to attach to every card (e.g. ['BIO101', 'L03']).

    Returns:
        CSV string properly escaped according to RFC 4180.
    """
    output = io.StringIO()
    # Add Anki header directives for UTF-8 and space-separated tags
    output.write("#separator:Comma\n")
    output.write("#html:true\n")
    output.write("#tags column:3\n")

    writer = csv.writer(output, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    tag_str = " ".join(t.replace(" ", "_") for t in (tags or []) if t.strip())

    for card in cards:
        # Replace newlines with <br> for clean rendering in Anki flashcard viewer
        front_html = card.front.replace("\n", "<br>")
        back_html = card.back.replace("\n", "<br>")
        if card.source:
            back_html += f"<br><br><small style='color:gray;'>出處: {card.source}</small>"

        writer.writerow([front_html, back_html, tag_str])

    return output.getvalue()
