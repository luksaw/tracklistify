"""Text normalization utilities for track matching."""

import re
import unicodedata


class TrackNormalizer:
    """Normalize track metadata for better matching."""

    # Common variations to normalize
    REPLACEMENTS: dict[str, str] = {
        " & ": " and ",
        " vs ": " versus ",
        " vs. ": " versus ",
        " ft ": " featuring ",
        " ft. ": " featuring ",
        " feat ": " featuring ",
        " feat. ": " featuring ",
        " w/ ": " with ",
    }

    # Patterns to remove for comparison
    REMOVE_PATTERNS: list[str] = [
        r"\(Original Mix\)",
        r"\(Original\)",
        r"\(Radio Edit\)",
        r"\(Extended Mix\)",
        r"\(Extended\)",
        r"\(Club Mix\)",
        r"[\'\"\`]",  # Quotes
    ]

    # Patterns that indicate remix info (keep these separate)
    REMIX_PATTERN = re.compile(
        r"\(([^)]*(?:Remix|Mix|Edit|Version|Dub|Rework|Bootleg)[^)]*)\)",
        re.IGNORECASE,
    )

    def normalize(self, text: str) -> str:
        """Normalize text for comparison."""
        # Lowercase
        text = text.lower()

        # Unicode normalization (e.g., e -> e)
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")

        # Apply replacements
        for old, new in self.REPLACEMENTS.items():
            text = text.replace(old.lower(), new)

        # Remove patterns
        for pattern in self.REMOVE_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def normalize_for_search(self, text: str) -> str:
        """Normalize text for Spotify search query."""
        # More aggressive normalization for search
        text = self.normalize(text)

        # Remove label info in brackets
        text = re.sub(r"\[[^\]]+\]", "", text)

        # Remove remix info for broader search
        text = self.REMIX_PATTERN.sub("", text)

        # Remove special characters except spaces
        text = re.sub(r"[^\w\s]", " ", text)

        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def extract_artists(self, artist_string: str) -> list[str]:
        """Split artist string into individual artists."""
        # Normalize first
        text = artist_string.lower()

        # Split on common separators (including + for collaborations)
        artists = re.split(
            r"\s*[,&+]\s*|\s+(?:and|vs\.?|versus|featuring|feat\.?|ft\.?|with|w/|x)\s+",
            text,
            flags=re.IGNORECASE,
        )

        return [a.strip() for a in artists if a.strip()]

    def extract_remix_info(self, title: str) -> tuple[str, str | None]:
        """Extract remix info from title, return (clean_title, remix_info)."""
        match = self.REMIX_PATTERN.search(title)
        if match:
            remix_info = match.group(1)
            clean_title = self.REMIX_PATTERN.sub("", title).strip()
            return clean_title, remix_info
        return title, None
