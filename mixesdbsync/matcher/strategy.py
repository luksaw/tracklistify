"""Multi-strategy track matching."""

from dataclasses import dataclass, field
from enum import Enum, auto

from mixesdbsync.config import MatcherConfig
from mixesdbsync.matcher.normalizer import TrackNormalizer
from mixesdbsync.matcher.scorer import TrackScorer
from mixesdbsync.mixesdb.models import MixTrack
from mixesdbsync.spotify.client import SpotifyClient
from mixesdbsync.spotify.models import SpotifyTrack


class MatchConfidence(Enum):
    """Confidence level of a track match."""

    EXACT = auto()  # >95 score
    HIGH = auto()  # 90-95 score
    MEDIUM = auto()  # 80-90 score
    LOW = auto()  # <80 score
    NO_MATCH = auto()  # No results

    @classmethod
    def from_score(cls, score: float) -> "MatchConfidence":
        """Get confidence level from score."""
        if score >= 95:
            return cls.EXACT
        elif score >= 90:
            return cls.HIGH
        elif score >= 80:
            return cls.MEDIUM
        else:
            return cls.LOW


@dataclass
class MatchResult:
    """Result of matching a track."""

    mixesdb_track: MixTrack
    spotify_track: SpotifyTrack | None
    confidence: MatchConfidence
    score: float
    search_strategy: str
    alternatives: list[SpotifyTrack] = field(default_factory=list)

    @property
    def matched(self) -> bool:
        """Check if a match was found."""
        return self.spotify_track is not None and self.confidence != MatchConfidence.NO_MATCH


class TrackMatcher:
    """Multi-strategy track matching engine."""

    def __init__(
        self,
        spotify_client: SpotifyClient,
        config: MatcherConfig | None = None,
    ):
        self.spotify = spotify_client
        self.config = config or MatcherConfig()
        self.normalizer = TrackNormalizer()
        self.scorer = TrackScorer()

    def find_match(self, track: MixTrack) -> MatchResult:
        """Find best Spotify match using cascading strategies."""
        strategies = [
            ("exact", self._exact_search),
            ("normalized", self._normalized_search),
            ("artist_title", self._artist_title_search),
            ("title_only", self._title_only_search),
        ]

        best_result: MatchResult | None = None

        for strategy_name, strategy_func in strategies:
            result = strategy_func(track, strategy_name)

            # Return immediately on high confidence match
            if result.confidence in (MatchConfidence.EXACT, MatchConfidence.HIGH):
                return result

            # Keep track of best result
            if best_result is None or result.score > best_result.score:
                best_result = result

        return best_result or self._no_match(track, "none")

    def _exact_search(self, track: MixTrack, strategy_name: str) -> MatchResult:
        """Try exact artist + title search."""
        results = self.spotify.search_track_exact(track.artist, track.title, limit=5)
        return self._evaluate_results(track, results, strategy_name)

    def _normalized_search(self, track: MixTrack, strategy_name: str) -> MatchResult:
        """Search with normalized text."""
        artist = self.normalizer.normalize_for_search(track.artist)
        title = self.normalizer.normalize_for_search(track.title)
        query = f"{artist} {title}"
        results = self.spotify.search_track(query, limit=10)
        return self._evaluate_results(track, results, strategy_name)

    def _artist_title_search(self, track: MixTrack, strategy_name: str) -> MatchResult:
        """Search with separate artist and title terms."""
        # Get primary artist
        artists = self.normalizer.extract_artists(track.artist)
        primary_artist = artists[0] if artists else track.artist

        # Clean title (remove remix info for broader search)
        clean_title, _ = self.normalizer.extract_remix_info(track.title)
        clean_title = self.normalizer.normalize_for_search(clean_title)

        query = f'artist:"{primary_artist}" {clean_title}'
        results = self.spotify.search_track(query, limit=10)
        return self._evaluate_results(track, results, strategy_name)

    def _title_only_search(self, track: MixTrack, strategy_name: str) -> MatchResult:
        """Search by title only (for rare/obscure artists)."""
        clean_title, remix = self.normalizer.extract_remix_info(track.title)
        query = f'track:"{clean_title}"'
        results = self.spotify.search_track(query, limit=20)

        # Filter by artist similarity
        if results:
            scored_results = []
            for r in results:
                score = self.scorer.score_match(track, r)
                scored_results.append((r, score))
            scored_results.sort(key=lambda x: x[1], reverse=True)
            results = [r for r, _ in scored_results[:10]]

        return self._evaluate_results(track, results, strategy_name)

    def _evaluate_results(
        self,
        track: MixTrack,
        results: list[SpotifyTrack],
        strategy_name: str,
    ) -> MatchResult:
        """Evaluate search results and return best match."""
        if not results:
            return self._no_match(track, strategy_name)

        # Score all results
        scored = []
        for result in results:
            score = self.scorer.score_match(track, result)
            scored.append((result, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        best_track, best_score = scored[0]
        confidence = MatchConfidence.from_score(best_score)

        # Filter based on min score threshold
        if best_score < self.config.min_score:
            if not self.config.include_low_confidence:
                return MatchResult(
                    mixesdb_track=track,
                    spotify_track=None,
                    confidence=MatchConfidence.NO_MATCH,
                    score=best_score,
                    search_strategy=strategy_name,
                    alternatives=[r for r, _ in scored[:5]],
                )

        return MatchResult(
            mixesdb_track=track,
            spotify_track=best_track,
            confidence=confidence,
            score=best_score,
            search_strategy=strategy_name,
            alternatives=[r for r, _ in scored[1:5]],
        )

    def _no_match(self, track: MixTrack, strategy_name: str) -> MatchResult:
        """Create a no-match result."""
        return MatchResult(
            mixesdb_track=track,
            spotify_track=None,
            confidence=MatchConfidence.NO_MATCH,
            score=0.0,
            search_strategy=strategy_name,
            alternatives=[],
        )
