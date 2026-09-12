"""
Series Architect - Main Recommender Module

This is the main entry point for the recommendation system.
UI/API layer should call get_recommendations() from this module.
"""

import sys
import os

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from data_layer.db_utils import fetch_query

# Try relative imports first, fall back to absolute
try:
    from .filters import apply_filters
    from .similarity_engine import get_recommendations as calc_recommendations
    from .feature_builder import get_series_data, clear_cache, preload_series_data
    from .config import TOP_N_DEFAULT, DEBUG_MODE, GENRE_ID_TO_NAME
except ImportError:
    from filters import apply_filters
    from similarity_engine import get_recommendations as calc_recommendations
    from feature_builder import get_series_data, clear_cache
    from config import TOP_N_DEFAULT, DEBUG_MODE, GENRE_ID_TO_NAME


# =====================================
# Main Recommendation Function
# =====================================

def get_recommendations(user_ratings, filters=None, top_n=None, weights=None):
    """
    Get personalized series recommendations.
    
    This is the MAIN function that the UI/API should call.
    
    Args:
        user_ratings: List of tuples with user ratings
                     Format: [(tmdb_id, rating, is_anchor), ...]
                     - rating: 1 (like), -1 (dislike)
                     - is_anchor: True/False (optional, defaults to False)
                     
        filters: Dict of filter criteria (all optional, None = no filter)
                {
                    'languages': ['en', 'ko', ...] or None,
                    'status': ['Running', 'Ended'] or None,
                    'decades': [2000, 2010, 2020] or None,
                    'genres': [18, 80, ...] or None  (genre_ids)
                }
        
        top_n: Number of recommendations to return (default: 10)
        weights: Custom feature weights dict (optional)
    
    Returns:
        list: List of recommendation dicts, sorted by score
              Each dict contains:
              {
                  'tmdb_id': int,
                  'title_en': str,
                  'title_he': str,
                  'score': float (0-1),
                  'poster_path': str,
                  'overview': str,
                  'popularity': float,
                  'first_air_date': str,
                  'status': str,
                  'origin_country': str,
                  'number_of_seasons': int,
                  'genres': [str, str, ...]  (genre names)
              }
    
    Example:
        user_ratings = [
            (1396, 1, True),   # Breaking Bad - Like (Anchor)
            (60059, 1, False), # Better Call Saul - Like
            (1668, -1, False)  # Friends - Dislike
        ]
        
        filters = {
            'languages': ['en'],
            'status': ['Running', 'Ended'],
            'decades': [2000, 2010, 2020],
            'genres': [18, 80]  # Drama, Crime
        }
        
        recommendations = get_recommendations(user_ratings, filters, top_n=10)
    """
    if top_n is None:
        top_n = TOP_N_DEFAULT
    
    if filters is None:
        filters = {}
    
    if DEBUG_MODE:
        print("\n" + "="*60)
        print("STARTING RECOMMENDATION ENGINE")
        print("="*60)
        print(f"User Ratings: {len(user_ratings)}")
        print(f"Filters: {filters}")
        print(f"Top N: {top_n}")
    
    # Step 1: Apply filters to get candidate pool
    if DEBUG_MODE:
        print("\n[STEP 1] Applying filters...")
    
    candidate_ids = apply_filters(filters)
    
    if not candidate_ids:
        if DEBUG_MODE:
            print("[ERROR] No candidates found after filtering!")
        return []
    
    if DEBUG_MODE:
        print(f"[STEP 1] Found {len(candidate_ids)} candidates")


    # Step 1.5: Preload all relevant series data in bulk (avoids N+1 queries)
    all_relevant_ids = list(set(candidate_ids) | set(uid for uid, _, _ in user_ratings))
    preload_series_data(all_relevant_ids)



    # Step 2: Calculate recommendation scores
    if DEBUG_MODE:
        print("\n[STEP 2] Calculating similarities...")
    
    scored_results = calc_recommendations(
        user_ratings=user_ratings,
        candidate_ids=candidate_ids,
        filters=filters,
        top_n=top_n,
        weights=weights
    )
    
    if not scored_results:
        if DEBUG_MODE:
            print("[ERROR] No recommendations generated!")
        return []
    
    if DEBUG_MODE:
        print(f"[STEP 2] Generated {len(scored_results)} recommendations")
    
    # Step 3: Enrich with metadata
    if DEBUG_MODE:
        print("\n[STEP 3] Enriching with metadata...")
    
    recommendations = enrich_recommendations(scored_results)
    
    if DEBUG_MODE:
        print(f"[STEP 3] Enriched {len(recommendations)} recommendations")
        print("\n" + "="*60)
        print("RECOMMENDATION ENGINE COMPLETE")
        print("="*60 + "\n")
    
    return recommendations


# =====================================
# Data Enrichment
# =====================================

def enrich_recommendations(scored_results):
    """
    Enrich recommendation results with full metadata.
    
    Args:
        scored_results: List of (tmdb_id, score) tuples
    
    Returns:
        list: List of enriched recommendation dicts
    """
    recommendations = []
    
    for tmdb_id, score in scored_results:
        # Get series data
        series_data = get_series_data(tmdb_id)
        
        if not series_data:
            continue
        
        # Get genres
        genres = get_series_genres_names(tmdb_id)
        
        # Get Hebrew title
        title_he = get_hebrew_title(tmdb_id)
        
        # Build recommendation dict
        rec = {
            'tmdb_id': tmdb_id,
            'title_en': series_data.get('title_en', 'Unknown'),
            'title_he': title_he,
            'score': round(score, 3),
            'poster_path': series_data.get('poster_path'),
            'overview': series_data.get('overview'),
            'popularity': series_data.get('popularity'),
            'vote_average': series_data.get('vote_average'),
            'first_air_date': str(series_data.get('first_air_date')) if series_data.get('first_air_date') else None,
            'status': series_data.get('status'),
            'origin_country': series_data.get('origin_country'),
            'number_of_seasons': series_data.get('number_of_seasons'),
            'number_of_episodes': series_data.get('number_of_episodes'),
            'content_rating': series_data.get('content_rating'),
            'genres': genres
        }
        
        recommendations.append(rec)
    
    return recommendations


def get_series_genres_names(tmdb_id):
    """
    Get genre names for a series.
    
    Args:
        tmdb_id: Series ID
    
    Returns:
        list: List of genre names (e.g., ['Drama', 'Crime'])
    """
    query = """
        SELECT g.genre_name
        FROM series_genres sg
        JOIN genres g ON sg.genre_id = g.genre_id
        WHERE sg.tmdb_id = %s
    """
    
    results = fetch_query(query, (tmdb_id,))
    
    return [row[0] for row in results]


def get_hebrew_title(tmdb_id):
    """
    Get Hebrew title for a series.
    
    Args:
        tmdb_id: Series ID
    
    Returns:
        str: Hebrew title or None
    """
    query = "SELECT title_he FROM series WHERE tmdb_id = %s"
    result = fetch_query(query, (tmdb_id,))
    
    if result and result[0][0]:
        return result[0][0]
    
    return None


# =====================================
# Utility Functions
# =====================================

def get_series_details(tmdb_id):
    """
    Get full details for a single series (for UI display).
    
    Args:
        tmdb_id: Series ID
    
    Returns:
        dict: Series details with metadata
    """
    series_data = get_series_data(tmdb_id)
    
    if not series_data:
        return None
    
    genres = get_series_genres_names(tmdb_id)
    title_he = get_hebrew_title(tmdb_id)
    
    return {
        'tmdb_id': tmdb_id,
        'title_en': series_data.get('title_en'),
        'title_he': title_he,
        'poster_path': series_data.get('poster_path'),
        'overview': series_data.get('overview'),
        'popularity': series_data.get('popularity'),
        'vote_average': series_data.get('vote_average'),
        'first_air_date': str(series_data.get('first_air_date')) if series_data.get('first_air_date') else None,
        'last_air_date': str(series_data.get('last_air_date')) if series_data.get('last_air_date') else None,
        'status': series_data.get('status'),
        'origin_country': series_data.get('origin_country'),
        'original_language': series_data.get('original_language'),
        'number_of_seasons': series_data.get('number_of_seasons'),
        'number_of_episodes': series_data.get('number_of_episodes'),
        'content_rating': series_data.get('content_rating'),
        'adult': series_data.get('adult'),
        'genres': genres
    }


def search_series(query, limit=10):
    """
    Search for series by title (for rating selection UI).
    
    Args:
        query: Search query string
        limit: Maximum number of results
    
    Returns:
        list: List of series dicts matching the query
    """
    sql = """
        SELECT tmdb_id, title_en, title_he, first_air_date, poster_path
        FROM series
        WHERE LOWER(title_en) LIKE LOWER(%s) OR LOWER(title_he) LIKE LOWER(%s)
        ORDER BY popularity DESC
        LIMIT %s
    """
    
    search_pattern = f'%{query}%'
    results = fetch_query(sql, (search_pattern, search_pattern, limit))
    
    series_list = []
    for row in results:
        series_list.append({
            'tmdb_id': row[0],
            'title_en': row[1],
            'title_he': row[2],
            'first_air_date': str(row[3]) if row[3] else None,
            'poster_path': row[4]
        })
    
    return series_list


def get_popular_series(limit=20, language=None):
    """
    Get most popular series (for initial rating selection).
    
    Args:
        limit: Number of series to return
        language: Filter by language (optional)
    
    Returns:
        list: List of popular series dicts
    """
    if language:
        sql = """
            SELECT tmdb_id, title_en, title_he, first_air_date, poster_path, popularity
            FROM series
            WHERE original_language = %s
            ORDER BY popularity DESC
            LIMIT %s
        """
        results = fetch_query(sql, (language, limit))
    else:
        sql = """
            SELECT tmdb_id, title_en, title_he, first_air_date, poster_path, popularity
            FROM series
            ORDER BY popularity DESC
            LIMIT %s
        """
        results = fetch_query(sql, (limit,))
    
    series_list = []
    for row in results:
        series_list.append({
            'tmdb_id': row[0],
            'title_en': row[1],
            'title_he': row[2],
            'first_air_date': str(row[3]) if row[3] else None,
            'poster_path': row[4],
            'popularity': row[5]
        })
    
    return series_list


def reset_cache():
    """
    Clear all caches (useful between sessions or for testing).
    """
    clear_cache()
    if DEBUG_MODE:
        print("[CACHE] All caches cleared")


# =====================================
# Statistics & Analysis
# =====================================

def get_recommendation_stats():
    """
    Get statistics about the recommendation system.
    
    Returns:
        dict: Statistics about the database and system
    """
    stats = {}
    
    # Total series
    result = fetch_query("SELECT COUNT(*) FROM series")
    stats['total_series'] = result[0][0] if result else 0
    
    # Series by language
    result = fetch_query("""
        SELECT original_language, COUNT(*) 
        FROM series 
        GROUP BY original_language 
        ORDER BY COUNT(*) DESC
    """)
    stats['by_language'] = {row[0]: row[1] for row in result} if result else {}
    
    # Series by status
    result = fetch_query("""
        SELECT status, COUNT(*) 
        FROM series 
        GROUP BY status
    """)
    stats['by_status'] = {row[0]: row[1] for row in result} if result else {}
    
    # Series by decade
    result = fetch_query("""
        SELECT 
            (EXTRACT(YEAR FROM first_air_date)::int / 10) * 10 as decade,
            COUNT(*)
        FROM series
        WHERE first_air_date IS NOT NULL
        GROUP BY decade
        ORDER BY decade DESC
    """)
    stats['by_decade'] = {row[0]: row[1] for row in result} if result else {}
    
    # Top genres
    result = fetch_query("""
        SELECT g.genre_name, COUNT(*) as cnt
        FROM series_genres sg
        JOIN genres g ON sg.genre_id = g.genre_id
        GROUP BY g.genre_name
        ORDER BY cnt DESC
        LIMIT 10
    """)
    stats['top_genres'] = {row[0]: row[1] for row in result} if result else {}
    
    return stats
