"""
Series Architect - Logic Layer Configuration

This file contains all constants, weights, and settings for the recommendation engine.
Centralizing these values makes it easy to tune the algorithm without changing code.
"""

# =====================================
# Feature Weights (Must sum to 1.0)
# =====================================
FEATURE_WEIGHTS = {
    'genres': 0.30,              # Genre overlap (Jaccard similarity)
    'keywords': 0.35,            # Keywords/themes overlap (Top-K Jaccard)
    'year_proximity': 0.10,      # Release year/decade proximity
    'origin_country': 0.10,      # Same production country
    'popularity': 0.08,          # Similar popularity level
    'content_rating': 0.04,      # Similar age rating
    'number_of_seasons': 0.03    # Similar length
}

# Validate weights sum to 1.0
_TOTAL_WEIGHT = sum(FEATURE_WEIGHTS.values())
assert abs(_TOTAL_WEIGHT - 1.0) < 0.001, f"Weights must sum to 1.0, got {_TOTAL_WEIGHT}"

# =====================================
# User Rating Settings
# =====================================
# Rating values
RATING_LIKE = 1
RATING_DISLIKE = -1
RATING_NEUTRAL = 0

# Minimum requirements
MIN_LIKES = 5               # Minimum number of likes required
MIN_TOTAL_RATINGS = 10      # Minimum total ratings (likes + dislikes)

# Anchor boost
ANCHOR_MULTIPLIER = 2.0     # Multiplier for anchor series (is_anchor=True)

# =====================================
# Similarity & Filtering Settings
# =====================================
# Dislike exclusion
DISLIKE_EXCLUSION_THRESHOLD = 0.7  # Exclude series with >0.7 similarity to dislikes

# Recommendation output
TOP_N_DEFAULT = 10          # Default number of recommendations to return

# =====================================
# Feature Calculation Settings
# =====================================
# Keywords
TOP_KEYWORDS_COUNT = 10     # Use only top N keywords per series

# Year proximity
DECADE_DIFF_MAX = 10        # Maximum year difference for similarity calculation
                            # Series 10+ years apart get 0 similarity score

# Popularity normalization
POPULARITY_LOG_BASE = 10    # Log base for popularity normalization

# Seasons normalization
SEASONS_DIFF_MAX = 5        # Maximum season difference for similarity
                            # Series with 5+ season difference get 0 similarity

# =====================================
# Database Query Limits
# =====================================
MAX_CANDIDATES = 10000      # Maximum series to consider (safety limit)

# =====================================
# TMDB Reference Data (from actual database)
# =====================================

# Genre IDs grouped by main category
# For filtering, users select by main_category (e.g., "Drama")
# The system then includes all genre_ids under that category
GENRE_CATEGORIES = {
    'Action & Adventure': [10759, 37],
    'Animation': [16],
    'Comedy': [35],
    'Crime': [80],
    'Documentary': [99],
    'Drama': [18, 10766],  # Drama + Soap Opera
    'Family': [10751],
    'Kids': [10762],
    'News': [10763],
    'Reality': [10764],
    'Romance': [10749],
    'Sci-Fi & Fantasy': [10765],
    'Talk Show': [10767],
    'Thriller': [9648],
    'War & Politics': [10768]
}

# All genre IDs (for validation)
ALL_GENRE_IDS = [
    10759, 16, 35, 80, 99, 18, 10751, 10762,
    9648, 10763, 10764, 10749, 10765, 10766,
    10767, 10768, 37
]

# Genre ID to Name mapping
GENRE_ID_TO_NAME = {
    10759: "Action & Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    10762: "Kids",
    9648: "Mystery",
    10763: "News",
    10764: "Reality",
    10749: "Romance",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap Opera",
    10767: "Talk Show",
    10768: "War & Politics",
    37: "Western"
}

# Language codes (ISO 639-1) - only languages present in database
VALID_LANGUAGES = ['en', 'he', 'es', 'ja']

LANGUAGE_NAMES = {
    'en': 'English',
    'he': 'Hebrew',
    'es': 'Spanish',
    'ja': 'Japanese'
}

# =====================================
# Validation Settings
# =====================================
VALID_STATUSES = ['Running', 'Ended']
VALID_DECADES = [1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]

# =====================================
# Debugging & Logging
# =====================================
DEBUG_MODE = False          # Set to True for verbose output
LOG_SIMILARITY_SCORES = False  # Log individual similarity calculations