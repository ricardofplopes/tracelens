import imagehash
from difflib import SequenceMatcher
import structlog

logger = structlog.get_logger()

# Source confidence weights
SOURCE_CONFIDENCE = {
    "google_lens": 0.9,
    "bing_visual": 0.9,
    "yandex": 0.85,
    "tineye": 0.9,
    "fb_direct_lookup": 0.95,
    "saucenao": 0.8,
    "iqdb": 0.75,
    "social_media": 0.65,
    "wikimedia": 0.7,
    "web_search": 0.5,
}


def compute_hash_similarity(hash1: str | None, hash2: str | None) -> float:
    """Compute similarity between two perceptual hashes (0-1, 1=identical)."""
    if not hash1 or not hash2:
        return 0.0
    try:
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        distance = h1 - h2
        max_distance = len(h1.hash.flatten())
        similarity = 1.0 - (distance / max_distance)
        return max(0.0, similarity)
    except Exception:
        return 0.0


def compute_text_overlap(text1: str | None, text2: str | None) -> float:
    """Compute text similarity using SequenceMatcher (0-1)."""
    if not text1 or not text2:
        return 0.0
    text1 = text1.lower().strip()
    text2 = text2.lower().strip()
    if not text1 or not text2:
        return 0.0
    return SequenceMatcher(None, text1, text2).ratio()


def compute_entity_overlap(entities1: list[str], entities2: list[str]) -> float:
    """Compute Jaccard similarity between two entity lists (0-1)."""
    if not entities1 or not entities2:
        return 0.0
    set1 = {e.lower().strip() for e in entities1}
    set2 = {e.lower().strip() for e in entities2}
    if not set1 or not set2:
        return 0.0
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union) if union else 0.0


def score_candidate(
    candidate: dict,
    features: dict,
    provider_name: str,
) -> float:
    """Score a candidate result based on multiple signals.
    
    Returns confidence score 0-1.
    """
    scores = []
    weights = []

    # Perceptual hash similarity (if candidate has hash info)
    candidate_hash = candidate.get("metadata", {}).get("phash")
    if candidate_hash and features.get("phash"):
        hash_sim = compute_hash_similarity(features["phash"], candidate_hash)
        scores.append(hash_sim)
        weights.append(3.0)

    # Exact hash match
    candidate_sha = candidate.get("metadata", {}).get("sha256")
    if candidate_sha and features.get("sha256"):
        if candidate_sha == features["sha256"]:
            scores.append(1.0)
            weights.append(5.0)
        else:
            scores.append(0.0)
            weights.append(1.0)

    # Text/OCR overlap
    candidate_text = candidate.get("extracted_text", "")
    ocr_text = features.get("ocr_text", "")
    if candidate_text and ocr_text:
        text_sim = compute_text_overlap(ocr_text, candidate_text)
        scores.append(text_sim)
        weights.append(1.5)

    # Provider's own similarity score
    provider_score = candidate.get("similarity_score", 0)
    if provider_score > 0:
        scores.append(min(provider_score, 1.0))
        weights.append(2.0)

    # Source confidence multiplier
    source_conf = SOURCE_CONFIDENCE.get(provider_name, 0.5)

    # Match type bonus: visual/similar matches from image-search providers
    # are inherently more relevant than text-only entity matches
    match_type = candidate.get("metadata", {}).get("type", "")
    match_type_from_candidate = candidate.get("match_type", "")

    if not scores:
        # No comparison signals — use provider score + source confidence
        # Apply a discount for text-only/entity matches without visual confirmation
        if match_type_from_candidate == "entity" or match_type == "text_extraction":
            return round(provider_score * source_conf * 0.5 if provider_score else source_conf * 0.15, 4)
        return round(provider_score * source_conf if provider_score else source_conf * 0.3, 4)

    weighted_sum = sum(s * w for s, w in zip(scores, weights))
    total_weight = sum(weights)
    raw_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Apply source confidence
    final_score = raw_score * 0.7 + source_conf * 0.3
    return round(min(1.0, max(0.0, final_score)), 4)


def cluster_duplicates(candidates: list[dict], threshold: float = 0.85) -> list[list[int]]:
    """Cluster duplicate results based on URL similarity.
    
    Returns list of clusters, where each cluster is a list of candidate indices.
    """
    n = len(candidates)
    visited = set()
    clusters = []

    for i in range(n):
        if i in visited:
            continue
        cluster = [i]
        visited.add(i)
        url_i = candidates[i].get("source_url", "")
        title_i = candidates[i].get("page_title", "")

        for j in range(i + 1, n):
            if j in visited:
                continue
            url_j = candidates[j].get("source_url", "")
            title_j = candidates[j].get("page_title", "")

            # Check URL similarity
            url_sim = compute_text_overlap(url_i, url_j)
            title_sim = compute_text_overlap(title_i, title_j)

            if url_sim > threshold or title_sim > threshold:
                cluster.append(j)
                visited.add(j)

        clusters.append(cluster)

    return clusters
