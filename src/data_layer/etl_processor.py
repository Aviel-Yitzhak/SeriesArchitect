import requests
import os
import sys

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from .db_utils import execute_query
except ImportError:
    from db_utils import execute_query

from dotenv import load_dotenv

load_dotenv()
TMDB_TOKEN = os.getenv('TMDB_TOKEN')
HEADERS = {
    "Authorization": f"Bearer {TMDB_TOKEN}",
    "accept": "application/json"
}


def discover_series_ids(lang_code="en", sort_by="popularity.desc", pages=1):
    """
    Fetches a list of series IDs from TMDB based on language and popularity.

    :param lang_code: The original language to filter by (e.g., 'en', 'es', 'he').
    :param sort_by: Sorting criterion (default: popularity. Desc).
    :param pages: Number of pages to fetch (20 items per page).
    :return: A list of integer TMDB IDs.
    """
    all_ids = []
    base_url = "https://api.themoviedb.org/3/discover/tv"

    for page in range(1, pages + 1):
        params = {
            "language": "he-IL",
            "sort_by": sort_by,
            "page": page,
            "with_original_language": lang_code
        }
        try:
            response = requests.get(base_url, headers=HEADERS, params=params)
            if response.status_code == 200:
                results = response.json().get("results", [])
                all_ids.extend([s["id"] for s in results])
        except Exception as e:
            print(f"Error discovering page {page}: {e}")

    return all_ids


def clean_date(date_str):
    """
    Helper function to convert empty date strings to None (NULL in SQL).
    """
    if not date_str or date_str.strip() == "":
        return None
    return date_str


def fetch_raw_data(tmdb_id):
    """
    Fetches comprehensive data for a single series from TMDB.
    Aggregates data from multiple endpoints: Details (HE/EN), Keywords, Providers, and Content Ratings.
    Applies logic for Status normalization, Country fixing, and TBA providers.

    :param tmdb_id: The TMDB ID of the series.
    :return: A dictionary containing processed series data, or None if failed.
    """
    try:
        # 1. Fetch basic info in Hebrew
        url_he = f"https://api.themoviedb.org/3/tv/{tmdb_id}?language=he-IL"
        data_he = requests.get(url_he, headers=HEADERS).json()

        # 2. Fetch basic info in English (fallback for titles/overview)
        url_en = f"https://api.themoviedb.org/3/tv/{tmdb_id}?language=en-US"
        data_en = requests.get(url_en, headers=HEADERS).json()

        # 3. Fetch Keywords
        url_keywords = f"https://api.themoviedb.org/3/tv/{tmdb_id}/keywords"
        keywords_data = requests.get(url_keywords, headers=HEADERS).json()

        # 4. Fetch Watch Providers
        url_providers = f"https://api.themoviedb.org/3/tv/{tmdb_id}/watch/providers"
        providers_data = requests.get(url_providers, headers=HEADERS).json()

        # 5. Fetch Content Ratings
        ratings_url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/content_ratings"
        ratings_data = requests.get(ratings_url, headers=HEADERS).json()

        # Extract Content Rating (Prefer 'IL', fallback to 'US')
        content_rating = "NR"
        for r in ratings_data.get('results', []):
            if r['iso_3166_1'] == 'IL':
                content_rating = r['rating']
                break
            elif r['iso_3166_1'] == 'US' and content_rating == "NR":
                content_rating = r['rating']

        # --- Status Normalization Logic ---
        raw_status = data_he.get('status')
        final_status = raw_status
        if raw_status == "Returning Series":
            final_status = "Running"
        elif raw_status in ["Ended", "Canceled"]:
            final_status = "Ended"

        # --- Origin Country Logic ---
        # Checks if list exists instead of defaulting blindly
        origin_country = "Unknown"
        countries_list = data_he.get('origin_country', [])
        if countries_list and len(countries_list) > 0:
            origin_country = countries_list[0]

        # --- Providers Logic (TBA Support) ---
        # Path: results -> IL -> flatrate
        # Using .get() ensures no crash if keys are missing
        il_providers = providers_data.get('results', {}).get('IL', {}).get('flatrate', [])

        final_providers = []
        if il_providers:
            final_providers = il_providers
        else:
            # Create a virtual 'TBA' provider if none exist
            final_providers = [{
                'provider_id': 0,
                'provider_name': 'TBA',
                'logo_path': None
            }]

        return {
            'tmdb_id': tmdb_id,
            'title_he': data_he.get('name'),
            'title_en': data_en.get('name'),
            'overview': data_he.get('overview') or data_en.get('overview'),
            'popularity': data_he.get('popularity'),
            'poster_path': data_en.get('poster_path') or data_he.get('poster_path'),
            'vote_average': data_en.get('vote_average'),
            'original_language': data_he.get('original_language'),
            'origin_country': origin_country,
            'status': final_status,
            'adult': data_he.get('adult', False),
            'first_air_date': clean_date(data_he.get('first_air_date')),
            'last_air_date': clean_date(data_he.get('last_air_date')),
            'number_of_seasons': data_he.get('number_of_seasons'),
            'number_of_episodes': data_he.get('number_of_episodes'),
            'content_rating': content_rating,
            'genres': data_he.get('genres', []),
            'keywords': keywords_data.get('results', []),
            'providers': final_providers
        }

    except Exception as e:
        print(f"Error fetching raw data for ID {tmdb_id}: {e}")
        return None


def save_to_db(data):
    """
    Saves the processed data to the database using Upsert logic.
    Handles Series, Genres, Keywords, and Providers tables.
    """
    if not data:
        return

    # 1. Series Table (Upsert)
    query_series = """
            INSERT INTO series (
                tmdb_id, title_he, title_en, overview, popularity, poster_path,
                original_language, origin_country, status, adult,
                first_air_date, last_air_date, number_of_seasons, number_of_episodes,
                content_rating, vote_average
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tmdb_id) DO UPDATE SET
                title_he = EXCLUDED.title_he,
                title_en = EXCLUDED.title_en,
                overview = EXCLUDED.overview,
                popularity = EXCLUDED.popularity,
                poster_path = EXCLUDED.poster_path,
                status = EXCLUDED.status,
                origin_country = EXCLUDED.origin_country,
                number_of_seasons = EXCLUDED.number_of_seasons,
                number_of_episodes = EXCLUDED.number_of_episodes,
                content_rating = EXCLUDED.content_rating,
                vote_average = EXCLUDED.vote_average;
        """
    execute_query(query_series, (
        data['tmdb_id'], data['title_he'], data['title_en'], data['overview'], data['popularity'],
        data['poster_path'], data['original_language'], data['origin_country'], data['status'],
        data['adult'], data['first_air_date'], data['last_air_date'],
        data['number_of_seasons'], data['number_of_episodes'], data['content_rating'],
        data['vote_average']
    ), fetch=False)

    # 2. Genres
    for genre in data['genres']:
        execute_query(
            "INSERT INTO genres (genre_id, genre_name, main_category) VALUES (%s, %s, %s) ON CONFLICT (genre_id) DO NOTHING",
            (genre['id'], genre['name'], genre['name']), fetch=False
        )
        execute_query(
            "INSERT INTO series_genres (tmdb_id, genre_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (data['tmdb_id'], genre['id']), fetch=False
        )

    # 3. Keywords
    for kw in data['keywords']:
        execute_query(
            "INSERT INTO keywords (keyword_id, name) VALUES (%s, %s) ON CONFLICT (keyword_id) DO NOTHING",
            (kw['id'], kw['name']), fetch=False
        )
        execute_query(
            "INSERT INTO series_keywords (tmdb_id, keyword_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (data['tmdb_id'], kw['id']), fetch=False
        )

    # 4. Providers
    # Clean old availability for IL before inserting new data
    execute_query("DELETE FROM series_availability WHERE tmdb_id = %s AND country_code = 'IL'", (data['tmdb_id'],),
                  fetch=False)

    for prov in data['providers']:
        execute_query(
            "INSERT INTO streaming_providers (provider_id, provider_name, logo_path) VALUES (%s, %s, %s) ON CONFLICT (provider_id) DO NOTHING",
            (prov['provider_id'], prov['provider_name'], prov['logo_path']), fetch=False
        )
        execute_query(
            "INSERT INTO series_availability (tmdb_id, provider_id, country_code) VALUES (%s, %s, 'IL') ON CONFLICT DO NOTHING",
            (data['tmdb_id'], prov['provider_id']), fetch=False
        )
