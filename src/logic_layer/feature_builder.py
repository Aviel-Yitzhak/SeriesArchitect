"""
Series Architect - Feature Builder Module

Builds numerical feature vectors for each series.
These vectors are used to calculate cosine similarity between series.
"""

import sys
import os
import numpy as np
from math import log10

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from data_layer.db_utils import fetch_query

try:
    from .config import (
        FEATURE_WEIGHTS,
        TOP_KEYWORDS_COUNT,
        DECADE_DIFF_MAX,
        POPULARITY_LOG_BASE,
        SEASONS_DIFF_MAX,
        DEBUG_MODE
    )
except ImportError:
    from config import (
        FEATURE_WEIGHTS,
        TOP_KEYWORDS_COUNT,
        DECADE_DIFF_MAX,
        POPULARITY_LOG_BASE,
        SEASONS_DIFF_MAX,
        DEBUG_MODE
    )


# =====================================
# Cache for optimization
# =====================================
_SERIES_CACHE = {}
_GENRES_CACHE = {}
_KEYWORDS_CACHE = {}


def clear_cache():
    """Clear all caches (useful for testing)."""
    global _SERIES_CACHE, _GENRES_CACHE, _KEYWORDS_CACHE
    _SERIES_CACHE = {}
    _GENRES_CACHE = {}
    _KEYWORDS_CACHE = {}



def preload_series_data(tmdb_ids):
    """
    Bulk-loads series data, genres, and keywords for many IDs at once,
    filling the caches so individual lookups become instant (no DB round-trip).
    Dramatically reduces network round-trips when the DB is remote.
    """
    ids_to_fetch = list(set(tmdb_ids) - set(_SERIES_CACHE.keys()))
    if not ids_to_fetch:
        return

    placeholders = ','.join(['%s'] * len(ids_to_fetch))

    # 1. Bulk load series data
    query = f"""
        SELECT tmdb_id, title_en, overview, popularity, poster_path,
               original_language, origin_country, status, adult,
               first_air_date, last_air_date, number_of_seasons,
               number_of_episodes, content_rating
        FROM series WHERE tmdb_id IN ({placeholders})
    """
    rows = fetch_query(query, tuple(ids_to_fetch))
    for row in rows:
        _SERIES_CACHE[row[0]] = {
            'tmdb_id': row[0], 'title_en': row[1], 'overview': row[2],
            'popularity': row[3], 'poster_path': row[4], 'original_language': row[5],
            'origin_country': row[6], 'status': row[7], 'adult': row[8],
            'first_air_date': row[9], 'last_air_date': row[10],
            'number_of_seasons': row[11], 'number_of_episodes': row[12],
            'content_rating': row[13]
        }

    # 2. Bulk load genres
    query_g = f"SELECT tmdb_id, genre_id FROM series_genres WHERE tmdb_id IN ({placeholders})"
    genres_map = {}
    for tid, gid in fetch_query(query_g, tuple(ids_to_fetch)):
        genres_map.setdefault(tid, set()).add(gid)
    for tid in ids_to_fetch:
        _GENRES_CACHE[tid] = genres_map.get(tid, set())

    # 3. Bulk load keywords (top N per config)
    query_k = f"SELECT tmdb_id, keyword_id FROM series_keywords WHERE tmdb_id IN ({placeholders})"
    keywords_map = {}
    for tid, kid in fetch_query(query_k, tuple(ids_to_fetch)):
        keywords_map.setdefault(tid, set()).add(kid)
    for tid in ids_to_fetch:
        _KEYWORDS_CACHE[(tid, TOP_KEYWORDS_COUNT)] = set(
            list(keywords_map.get(tid, set()))[:TOP_KEYWORDS_COUNT]
        )



# =====================================
# Data Fetching Functions
# =====================================

def get_series_data(tmdb_id):
    """
    Fetch all data for a series from database.
    Uses caching to avoid repeated queries.
    
    Returns:
        dict: Series data or None if not found
    """
    if tmdb_id in _SERIES_CACHE:
        return _SERIES_CACHE[tmdb_id]

    query = """
        SELECT tmdb_id, title_en, overview, popularity, poster_path,
               original_language, origin_country, status, adult,
               first_air_date, last_air_date, number_of_seasons,
               number_of_episodes, content_rating, vote_average, embedding
        FROM series
        WHERE tmdb_id = %s
    """
    
    result = fetch_query(query, (tmdb_id,))
    
    if not result:
        return None

    row = result[0]
    data = {
        'tmdb_id': row[0],
        'title_en': row[1],
        'overview': row[2],
        'popularity': row[3],
        'poster_path': row[4],
        'original_language': row[5],
        'origin_country': row[6],
        'status': row[7],
        'adult': row[8],
        'first_air_date': row[9],
        'last_air_date': row[10],
        'number_of_seasons': row[11],
        'number_of_episodes': row[12],
        'content_rating': row[13],
        'vote_average': row[14],
        'embedding': row[15]
    }
    
    _SERIES_CACHE[tmdb_id] = data
    return data


def get_series_genres(tmdb_id):
    """
    Get list of genre_ids for a series.
    Uses caching.
    
    Returns:
        set: Set of genre_ids
    """
    if tmdb_id in _GENRES_CACHE:
        return _GENRES_CACHE[tmdb_id]
    
    query = "SELECT genre_id FROM series_genres WHERE tmdb_id = %s"
    results = fetch_query(query, (tmdb_id,))
    
    genres = set(row[0] for row in results)
    _GENRES_CACHE[tmdb_id] = genres
    
    return genres


def get_series_keywords(tmdb_id, top_n=None):
    """
    Get list of keyword_ids for a series.
    Uses caching.
    
    Args:
        tmdb_id: Series ID
        top_n: Limit to top N keywords (optional)
    
    Returns:
        set: Set of keyword_ids
    """
    cache_key = (tmdb_id, top_n)
    
    if cache_key in _KEYWORDS_CACHE:
        return _KEYWORDS_CACHE[cache_key]
    
    # Note: TMDB doesn't provide keyword weights, so we just take first N
    query = "SELECT keyword_id FROM series_keywords WHERE tmdb_id = %s"
    
    if top_n:
        query += f" LIMIT {top_n}"
    
    results = fetch_query(query, (tmdb_id,))
    
    keywords = set(row[0] for row in results)
    _KEYWORDS_CACHE[cache_key] = keywords
    
    return keywords


# =====================================
# Feature Calculation Functions
# =====================================

def jaccard_similarity(set_a, set_b):
    """
    Calculate Jaccard similarity between two sets.
    
    Formula: |A ∩ B| / |A ∪ B|
    
    Returns:
        float: Similarity score between 0 and 1
    """
    if not set_a or not set_b:
        return 0.0
    
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    
    if union == 0:
        return 0.0
    
    return intersection / union


def calculate_genres_similarity(tmdb_id_a, tmdb_id_b):
    """
    Calculate genre similarity using Jaccard index.
    
    Returns:
        float: Similarity score between 0 and 1
    """
    genres_a = get_series_genres(tmdb_id_a)
    genres_b = get_series_genres(tmdb_id_b)
    
    return jaccard_similarity(genres_a, genres_b)


def calculate_keywords_similarity(tmdb_id_a, tmdb_id_b):
    """
    Calculate keywords similarity using Jaccard index on top keywords.
    
    Returns:
        float: Similarity score between 0 and 1
    """
    keywords_a = get_series_keywords(tmdb_id_a, top_n=TOP_KEYWORDS_COUNT)
    keywords_b = get_series_keywords(tmdb_id_b, top_n=TOP_KEYWORDS_COUNT)
    
    return jaccard_similarity(keywords_a, keywords_b)


def calculate_year_proximity(tmdb_id_a, tmdb_id_b):
    """
    Calculate year proximity based on first air date.
    
    Formula: max(0, 1 - year_diff / DECADE_DIFF_MAX)
    
    Returns:
        float: Similarity score between 0 and 1
    """
    data_a = get_series_data(tmdb_id_a)
    data_b = get_series_data(tmdb_id_b)
    
    if not data_a or not data_b:
        return 0.0
    
    date_a = data_a.get('first_air_date')
    date_b = data_b.get('first_air_date')
    
    if not date_a or not date_b:
        return 0.0
    
    year_a = date_a.year
    year_b = date_b.year
    
    year_diff = abs(year_a - year_b)
    
    # Normalize: 0 years = 1.0, DECADE_DIFF_MAX years = 0.0
    similarity = max(0, 1 - (year_diff / DECADE_DIFF_MAX))
    
    return similarity


def calculate_origin_country_similarity(tmdb_id_a, tmdb_id_b):
    """
    Calculate origin country similarity (binary: 1 if same, 0 if different).
    
    Returns:
        float: 1.0 if same country, 0.0 otherwise
    """
    data_a = get_series_data(tmdb_id_a)
    data_b = get_series_data(tmdb_id_b)
    
    if not data_a or not data_b:
        return 0.0
    
    country_a = data_a.get('origin_country')
    country_b = data_b.get('origin_country')
    
    if not country_a or not country_b:
        return 0.0
    
    return 1.0 if country_a == country_b else 0.0


def calculate_popularity_similarity(tmdb_id_a, tmdb_id_b):
    """
    Calculate popularity similarity using log-normalized distance.
    
    Uses log scale to reduce impact of extreme popularity differences.
    
    Returns:
        float: Similarity score between 0 and 1
    """
    data_a = get_series_data(tmdb_id_a)
    data_b = get_series_data(tmdb_id_b)
    
    if not data_a or not data_b:
        return 0.0
    
    pop_a = data_a.get('popularity', 0)
    pop_b = data_b.get('popularity', 0)
    
    if pop_a <= 0 or pop_b <= 0:
        return 0.0
    
    # Log normalization to reduce extreme differences
    log_a = log10(1 + pop_a)
    log_b = log10(1 + pop_b)
    
    # Calculate normalized distance
    max_log = max(log_a, log_b)
    if max_log == 0:
        return 1.0
    
    distance = abs(log_a - log_b) / max_log
    similarity = 1.0 - distance
    
    return max(0.0, similarity)


def calculate_content_rating_similarity(tmdb_id_a, tmdb_id_b):
    """
    Calculate content rating similarity using ordinal distance.
    
    Rating order: TV-Y < TV-Y7 < TV-G < TV-PG < TV-14 < TV-MA
    
    Returns:
        float: Similarity score between 0 and 1
    """
    # Rating hierarchy (lower number = more restrictive)
    RATING_ORDER = {
        'TV-Y': 0,
        'TV-Y7': 1,
        'TV-G': 2,
        'TV-PG': 3,
        'TV-14': 4,
        'TV-MA': 5,
        'NR': 3  # Not Rated = assume middle ground
    }
    
    data_a = get_series_data(tmdb_id_a)
    data_b = get_series_data(tmdb_id_b)
    
    if not data_a or not data_b:
        return 0.0
    
    rating_a = data_a.get('content_rating', 'NR')
    rating_b = data_b.get('content_rating', 'NR')
    
    # Get ordinal values
    ord_a = RATING_ORDER.get(rating_a, 3)  # Default to middle
    ord_b = RATING_ORDER.get(rating_b, 3)
    
    # Calculate distance (max distance is 5)
    distance = abs(ord_a - ord_b)
    similarity = 1.0 - (distance / 5.0)
    
    return max(0.0, similarity)


def calculate_seasons_similarity(tmdb_id_a, tmdb_id_b):
    """
    Calculate similarity based on number of seasons.
    
    Formula: max(0, 1 - season_diff / SEASONS_DIFF_MAX)
    
    Returns:
        float: Similarity score between 0 and 1
    """
    data_a = get_series_data(tmdb_id_a)
    data_b = get_series_data(tmdb_id_b)
    
    if not data_a or not data_b:
        return 0.0
    
    seasons_a = data_a.get('number_of_seasons', 0)
    seasons_b = data_b.get('number_of_seasons', 0)

    if seasons_a is None or seasons_b is None:
        return 0.0

    if seasons_a == 0 or seasons_b == 0:
        return 0.0
    
    season_diff = abs(seasons_a - seasons_b)
    similarity = max(0, 1 - (season_diff / SEASONS_DIFF_MAX))
    
    return similarity


# =====================================
# Weighted Similarity Calculation
# =====================================

def calculate_weighted_similarity(tmdb_id_a, tmdb_id_b, weights=None):
    """
    Calculate overall weighted similarity between two series.
    
    Args:
        tmdb_id_a: First series ID
        tmdb_id_b: Second series ID
        weights: Custom weights dict (uses FEATURE_WEIGHTS if None)
    
    Returns:
        float: Weighted similarity score between 0 and 1
    """
    if weights is None:
        weights = FEATURE_WEIGHTS
    
    # Calculate individual feature similarities
    similarities = {
        'genres': calculate_genres_similarity(tmdb_id_a, tmdb_id_b),
        'keywords': calculate_keywords_similarity(tmdb_id_a, tmdb_id_b),
        'year_proximity': calculate_year_proximity(tmdb_id_a, tmdb_id_b),
        'origin_country': calculate_origin_country_similarity(tmdb_id_a, tmdb_id_b),
        'popularity': calculate_popularity_similarity(tmdb_id_a, tmdb_id_b),
        'content_rating': calculate_content_rating_similarity(tmdb_id_a, tmdb_id_b),
        'number_of_seasons': calculate_seasons_similarity(tmdb_id_a, tmdb_id_b),
        'embedding': calculate_embedding_similarity(tmdb_id_a, tmdb_id_b),
    }
    
    # Calculate weighted sum
    total_similarity = 0.0
    for feature, weight in weights.items():
        if feature in similarities:
            total_similarity += similarities[feature] * weight
    
    if DEBUG_MODE:
        print(f"[SIMILARITY] {tmdb_id_a} vs {tmdb_id_b}:")
        for feature, sim in similarities.items():
            print(f"  {feature}: {sim:.3f} (weight: {weights.get(feature, 0):.2f})")
        print(f"  TOTAL: {total_similarity:.3f}")
    
    return total_similarity


# =====================================
# Batch Operations
# =====================================

def calculate_similarities_batch(reference_id, candidate_ids, weights=None):
    """
    Calculate similarities between one reference series and multiple candidates.
    
    Args:
        reference_id: Reference series ID
        candidate_ids: List of candidate series IDs
        weights: Custom weights dict (optional)
    
    Returns:
        list: List of tuples (candidate_id, similarity_score)
    """
    results = []
    
    for candidate_id in candidate_ids:
        if candidate_id == reference_id:
            continue  # Skip self-comparison
        
        similarity = calculate_weighted_similarity(reference_id, candidate_id, weights)
        results.append((candidate_id, similarity))
    
    return results

def _parse_vector(raw):
    """Converts the raw string/list returned from pgvector into a numpy array."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return np.array([float(x) for x in raw.strip('[]').split(',')])
    return np.array(raw)


def calculate_embedding_similarity(tmdb_id_a, tmdb_id_b):
    """
    Calculate semantic similarity using AI embeddings (cosine similarity).
    Captures tone/theme similarity that genres/keywords miss.
    """
    data_a = get_series_data(tmdb_id_a)
    data_b = get_series_data(tmdb_id_b)

    if not data_a or not data_b:
        return 0.0

    vec_a = _parse_vector(data_a.get('embedding'))
    vec_b = _parse_vector(data_b.get('embedding'))

    if vec_a is None or vec_b is None:
        return 0.0

    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    cosine = np.dot(vec_a, vec_b) / (norm_a * norm_b)

    # Cosine similarity ranges -1..1, normalize to 0..1 to match other features
    return float((cosine + 1) / 2)