"""Three-tier article deduplication: URL -> SimHash -> MinHash -> Semantic clustering."""

import hashlib
import uuid
from collections import defaultdict

import numpy as np
from datasketch import MinHash, MinHashLSH

# simhash may fail to build on Python 3.12+ (no pre-built wheel).
# Fall back to a simple token-set hash if unavailable.
try:
    from simhash import Simhash
    _HAS_SIMHASH = True
except (ImportError, OSError):
    _HAS_SIMHASH = False

    class Simhash:
        """Fallback: Jaccard-like token hash when simhash C extension unavailable."""
        def __init__(self, tokens=None, value=None):
            if value is not None:
                self.value = value
            elif tokens:
                self.value = hash(frozenset(tokens if isinstance(tokens, list) else [tokens])) & 0xFFFFFFFFFFFFFFFF
            else:
                self.value = 0

        def distance(self, other):
            # XOR + popcount approximation
            x = self.value ^ other.value
            return bin(x).count("1")

from news_terminal.utils.logger import get_logger

log = get_logger("dedup")


def _shingles(text: str, k: int = 3) -> set[str]:
    """Generate k-character shingles from text."""
    text = text.lower().strip()
    if len(text) < k:
        return {text}
    return {text[i : i + k] for i in range(len(text) - k + 1)}


def _compute_minhash(text: str, num_perm: int = 128) -> MinHash:
    mh = MinHash(num_perm=num_perm)
    for s in _shingles(text):
        mh.update(s.encode("utf-8"))
    return mh


class ArticleDeduplicator:
    """
    Three-tier dedup with optional semantic clustering.

    Layer 1: Exact URL match
    Layer 2: SimHash on title (Hamming distance <= 3)
    Layer 3: MinHash on content (Jaccard threshold 0.7)
    Layer 4: Semantic clustering via sentence-transformers (optional, loaded lazily)
    """

    SEMANTIC_THRESHOLD = 0.72  # Lowered from 0.75 — catches more "same story" pairs

    def __init__(self, seen_urls: list[str] = None, seen_hashes: list[int] = None,
                 saved_embeddings: dict[str, list] = None):
        self.seen_urls: set[str] = set(seen_urls or [])
        self.title_hashes: list[Simhash] = [Simhash(value=h) for h in (seen_hashes or [])]
        self.lsh = MinHashLSH(threshold=0.7, num_perm=128)
        self._lsh_count = 0
        self.clusters: dict[str, list[dict]] = defaultdict(list)
        self._model = None
        # Restore cluster embeddings from previous runs for cross-day rehash detection
        self._embeddings: dict[str, np.ndarray] = {}
        if saved_embeddings:
            for cid, emb_list in saved_embeddings.items():
                try:
                    self._embeddings[cid] = np.array(emb_list, dtype=np.float32)
                except (ValueError, TypeError):
                    pass
            if self._embeddings:
                log.info("Restored %d cluster embeddings from previous run", len(self._embeddings))

    def _get_model(self):
        """Lazy-load sentence transformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
                log.info("Loaded sentence-transformers model")
            except (ImportError, OSError, Exception) as e:
                log.warning("Semantic clustering disabled — model load failed: %s", e)
        return self._model

    def deduplicate(self, articles: list[dict]) -> list[dict]:
        """
        Run all dedup layers on a list of articles.
        Returns deduplicated articles with cluster_id set where applicable.

        Merge strategy (#7): when a duplicate is detected, if the new version has better
        text_quality, replace the existing one. If the existing has a Gemini summary but
        the new one has full text, merge both.
        """
        # Sort so higher-quality articles come first (full > ai_summary > excerpt > headline)
        quality_rank = {"full": 0, "ai_summary": 1, "excerpt": 2, "headline": 3}
        articles = sorted(articles, key=lambda a: quality_rank.get(a.get("text_quality", "headline"), 3))

        result = []
        result_by_url = {}  # url -> index in result, for merge lookups
        stats = {"url_dup": 0, "title_dup": 0, "content_dup": 0, "merged": 0, "clustered": 0, "unique": 0}

        for article in articles:
            url = article["url"]
            title = article.get("title", "")
            text = article.get("text", "")

            # Layer 1: URL exact match
            if url in self.seen_urls:
                stats["url_dup"] += 1
                continue
            self.seen_urls.add(url)

            # Layer 2: SimHash on title — merge instead of skip if new version is better
            title_simhash = Simhash(title.lower().split())
            is_title_dup = False
            for existing in self.title_hashes:
                if title_simhash.distance(existing) <= 3:
                    is_title_dup = True
                    break
            if is_title_dup:
                # Check if this version has better quality than what we already have
                merged = self._try_merge(article, result)
                if merged:
                    stats["merged"] += 1
                else:
                    stats["title_dup"] += 1
                continue
            self.title_hashes.append(title_simhash)

            # Layer 3: MinHash on content
            if text and len(text) > 50:
                mh = _compute_minhash(text)
                key = f"mh_{self._lsh_count}"
                try:
                    matches = self.lsh.query(mh)
                    if matches:
                        merged = self._try_merge(article, result)
                        if merged:
                            stats["merged"] += 1
                        else:
                            stats["content_dup"] += 1
                        continue
                    self.lsh.insert(key, mh)
                    self._lsh_count += 1
                except Exception:
                    pass

            # Layer 4: Semantic clustering (assign cluster_id if similar)
            cluster_id = self._find_cluster(article)
            if cluster_id:
                article["cluster_id"] = cluster_id
                article["dedup_method"] = "clustered"
                stats["clustered"] += 1
            else:
                cluster_id = f"evt_{uuid.uuid4().hex[:8]}"
                article["cluster_id"] = cluster_id
                article["dedup_method"] = "unique"
                self._register_cluster(cluster_id, article)
                stats["unique"] += 1

            result.append(article)

        log.info(
            "Dedup results: %d unique, %d clustered, %d merged, removed %d URL / %d title / %d content dups",
            stats["unique"], stats["clustered"], stats["merged"],
            stats["url_dup"], stats["title_dup"], stats["content_dup"],
        )
        return result

    def _try_merge(self, new_article: dict, result: list[dict]) -> bool:
        """
        Try to merge new_article into an existing result with the same story (#7).
        If new has better text, upgrade existing. If existing has an AI summary, preserve it.
        Returns True if merge happened.
        """
        quality_rank = {"full": 0, "ai_summary": 1, "excerpt": 2, "headline": 3}
        new_q = quality_rank.get(new_article.get("text_quality", "headline"), 3)

        # Find the best matching existing article by title similarity
        new_words = set(new_article.get("title", "").lower().split())
        best_idx = None
        best_overlap = 0
        for i, existing in enumerate(result):
            ex_words = set(existing.get("title", "").lower().split())
            if not ex_words:
                continue
            overlap = len(new_words & ex_words) / max(len(new_words | ex_words), 1)
            if overlap > best_overlap and overlap > 0.4:
                best_overlap = overlap
                best_idx = i

        if best_idx is None:
            return False

        existing = result[best_idx]
        ex_q = quality_rank.get(existing.get("text_quality", "headline"), 3)

        # If new article has better text, upgrade
        if new_q < ex_q:
            # Preserve existing summary if it was AI-generated
            old_summary = existing.get("summary") if existing.get("discovery_source") == "gemini_search" else None
            existing["text"] = new_article.get("text", existing["text"])
            existing["text_quality"] = new_article.get("text_quality", existing["text_quality"])
            if old_summary and not new_article.get("summary"):
                existing["summary"] = old_summary

        # If new article has a summary but existing doesn't, attach it
        if new_article.get("summary") and not existing.get("summary"):
            existing["summary"] = new_article["summary"]

        # Carry over image if missing
        if new_article.get("image_url") and not existing.get("image_url"):
            existing["image_url"] = new_article["image_url"]

        return True

    def _find_cluster(self, article: dict) -> str | None:
        """Find an existing cluster this article belongs to via semantic similarity."""
        model = self._get_model()
        if model is None:
            return None

        text = (article.get("title", "") + " " + article.get("text", "")[:500]).strip()
        if not text:
            return None

        embedding = model.encode(text, normalize_embeddings=True)

        for cluster_id, cluster_emb in self._embeddings.items():
            similarity = float(np.dot(embedding, cluster_emb))
            if similarity > self.SEMANTIC_THRESHOLD:
                return cluster_id

        return None

    def _register_cluster(self, cluster_id: str, article: dict) -> None:
        """Register a new cluster with its embedding."""
        model = self._get_model()
        if model is None:
            return

        text = (article.get("title", "") + " " + article.get("text", "")[:500]).strip()
        if text:
            self._embeddings[cluster_id] = model.encode(text, normalize_embeddings=True)

    def get_state(self) -> dict:
        """Export state for persistence between runs, including top 50 cluster embeddings."""
        # Keep only the 50 most recent cluster embeddings to limit state size (~200KB)
        recent_embeddings = dict(list(self._embeddings.items())[-50:])
        return {
            "seen_urls": list(self.seen_urls),
            "title_hashes": [h.value for h in self.title_hashes],
            "cluster_embeddings": {
                cid: emb.tolist() for cid, emb in recent_embeddings.items()
            },
        }
