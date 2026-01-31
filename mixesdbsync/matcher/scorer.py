"""Fuzzy scoring for track matching."""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from mixesdbsync.matcher.normalizer import TrackNormalizer
from mixesdbsync.mixesdb.models import MixTrack
from mixesdbsync.spotify.models import SpotifyTrack


@dataclass
class ScorerWeights:
    """Weights for different scoring components."""

    artist: float = 0.4
    title: float = 0.6


class TrackScorer:
    """Score track similarity using multiple metrics - STRICT mode."""

    # Pattern to extract remix/version info in parentheses: (Artist Remix)
    REMIX_PAREN_PATTERN = re.compile(
        r"\(([^)]*(?:Remix|Mix|Edit|Version|Dub|Rework|Bootleg|Reconstructed)[^)]*)\)",
        re.IGNORECASE,
    )

    # Pattern to extract remix/version info after dash: " - Artist Remix"
    REMIX_DASH_PATTERN = re.compile(
        r"\s+-\s+(.*?(?:Remix|Mix|Edit|Version|Dub|Rework|Bootleg|Reconstructed).*)$",
        re.IGNORECASE,
    )

    # Pattern to detect remaster info (should be ignored - same song, better audio)
    REMASTER_PATTERN = re.compile(
        r"\s*[-–]\s*Remaster(?:ed)?\s*\d*\s*$|\(Remaster(?:ed)?\s*\d*\)",
        re.IGNORECASE,
    )

    def __init__(self, weights: ScorerWeights | None = None):
        self.weights = weights or ScorerWeights()
        self.normalizer = TrackNormalizer()

    def score_match(
        self,
        mixesdb_track: MixTrack,
        spotify_track: SpotifyTrack,
    ) -> float:
        """
        Calculate match score between MixesDB and Spotify tracks.
        Returns score 0-100. STRICT matching - remix/version must match.
        """
        # Extract remix info from both (handles both formats)
        mdb_remix = self._extract_remix(mixesdb_track.title)
        sp_remix = self._extract_remix(spotify_track.name)

        # Get base titles (without remix info)
        mdb_base_title = self._remove_remix(mixesdb_track.title)
        sp_base_title = self._remove_remix(spotify_track.name)

        # Normalize
        mdb_artist = self.normalizer.normalize(mixesdb_track.artist)
        mdb_base_title_norm = self.normalizer.normalize(mdb_base_title)
        sp_base_title_norm = self.normalizer.normalize(sp_base_title)

        # Score artist - ALL artists must be present
        artist_score = self._score_artist_strict(mdb_artist, spotify_track.artists)

        # Score base title
        title_score = self._score_title_strict(mdb_base_title_norm, sp_base_title_norm)

        # Score remix/version match - CRITICAL
        remix_score = self._score_remix(mdb_remix, sp_remix)

        # If remix info differs significantly, cap the score
        if mdb_remix and not sp_remix:
            # MixesDB has remix but Spotify doesn't - likely wrong version
            remix_score = 0
        elif not mdb_remix and sp_remix:
            # Spotify has remix but MixesDB doesn't - likely wrong version
            remix_score = 0

        # Weighted combination: artist 30%, title 40%, remix 30%
        final_score = (
            artist_score * 0.30 +
            title_score * 0.40 +
            remix_score * 0.30
        )

        return final_score

    def _extract_remix(self, title: str) -> str | None:
        """Extract remix/version info from title (handles both formats)."""
        # First strip remaster info - it's not a different version
        title = self.REMASTER_PATTERN.sub("", title).strip()

        # Try parentheses format first: "Track (Artist Remix)"
        match = self.REMIX_PAREN_PATTERN.search(title)
        if match:
            return match.group(1).lower().strip()

        # Try dash format: "Track - Artist Remix"
        match = self.REMIX_DASH_PATTERN.search(title)
        if match:
            return match.group(1).lower().strip()

        return None

    def _remove_remix(self, title: str) -> str:
        """Remove remix/version info from title (handles both formats)."""
        # Remove remaster info first (it's not a different version)
        title = self.REMASTER_PATTERN.sub("", title)
        # Remove parentheses format
        title = self.REMIX_PAREN_PATTERN.sub("", title)
        # Remove dash format
        title = self.REMIX_DASH_PATTERN.sub("", title)
        return title.strip()

    def _score_artist_strict(
        self,
        mdb_artist: str,
        sp_all_artists: list[str],
    ) -> float:
        """Score artist match - ALL MixesDB artists must be in Spotify."""
        mdb_artists = self.normalizer.extract_artists(mdb_artist)
        sp_artists_normalized = [self.normalizer.normalize(a) for a in sp_all_artists]

        if not mdb_artists:
            return 0.0

        # Check that ALL MixesDB artists are found in Spotify
        matched_count = 0
        for mdb_a in mdb_artists:
            best_match = 0.0
            for sp_a in sp_artists_normalized:
                score = fuzz.ratio(mdb_a, sp_a)
                best_match = max(best_match, score)
            if best_match >= 85:  # Require 85% match for each artist
                matched_count += 1

        # All artists must match
        if matched_count == len(mdb_artists):
            return 100.0
        elif matched_count > 0:
            # Partial match - penalize significantly
            return (matched_count / len(mdb_artists)) * 60
        else:
            return 0.0

    def _score_title_strict(self, mdb_title: str, sp_title: str) -> float:
        """Score title match - strict comparison."""
        if mdb_title == sp_title:
            return 100.0

        # Use strict ratio, not partial or token-based
        ratio = fuzz.ratio(mdb_title, sp_title)

        # Penalize if lengths are very different
        len_diff = abs(len(mdb_title) - len(sp_title))
        if len_diff > 10:
            ratio = ratio * 0.8

        return ratio

    def _score_remix(self, mdb_remix: str | None, sp_remix: str | None) -> float:
        """Score remix/version match."""
        # Both have no remix - perfect match
        if not mdb_remix and not sp_remix:
            return 100.0

        # One has remix, other doesn't - wrong version
        if (mdb_remix and not sp_remix) or (not mdb_remix and sp_remix):
            return 0.0

        # Both have remix - compare them
        if mdb_remix and sp_remix:
            # Normalize for comparison
            mdb_norm = self.normalizer.normalize(mdb_remix)
            sp_norm = self.normalizer.normalize(sp_remix)

            # Use token_set_ratio to handle word order and minor differences
            score = fuzz.token_set_ratio(mdb_norm, sp_norm)

            # Also check partial ratio for typos like "Angels" vs "Angles"
            partial_score = fuzz.partial_ratio(mdb_norm, sp_norm)
            score = max(score, partial_score)

            # Be somewhat lenient - allow for typos in remix artist names
            if score >= 75:
                return 100.0
            elif score >= 60:
                return 70.0
            else:
                return 0.0

        return 0.0
