"""
Series Architect - Flask Application
Main server file - Unified Screen with Sidebar
"""

from flask import Flask, render_template, request, session, jsonify
import sys
from pathlib import Path

# Add all necessary paths
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root / 'src'))
sys.path.insert(0, str(project_root / 'src' / 'logic_layer'))
sys.path.insert(0, str(project_root / 'src' / 'data_layer'))

from logic_layer.config import GENRE_CATEGORIES

app = Flask(__name__)
app.secret_key = 'series_architect_secret_key_2026'  # Change in production

# =====================================
# Routes
# =====================================

@app.route('/')
def index():
    """Main screen with sidebar filters and series rating"""
    return render_template('index.html', genres=list(GENRE_CATEGORIES.keys()))

@app.route('/api/get-series', methods=['POST'])
def get_series():
    """Get filtered series for rating"""
    import logic_layer.filters as filters_module
    import data_layer.db_utils as db_utils_module

    data = request.json

    # Build filters dict
    filters_dict = {}

    # Languages
    if data.get('languages') and len(data['languages']) > 0:
        filters_dict['languages'] = data['languages']

    # Genres - convert to genre IDs
    if data.get('genres') and len(data['genres']) > 0:
        # Convert genre names to IDs using GENRE_CATEGORIES
        genre_ids = []
        for genre_name in data['genres']:
            if genre_name in GENRE_CATEGORIES:
                # GENRE_CATEGORIES[name] returns a list, so extend instead of append
                category_ids = GENRE_CATEGORIES[genre_name]
                if isinstance(category_ids, list):
                    genre_ids.extend(category_ids)
                else:
                    genre_ids.append(category_ids)
        if genre_ids:
            filters_dict['genres'] = genre_ids

        print(f"[DEBUG] Genre names: {data['genres']}")
        print(f"[DEBUG] Genre IDs: {genre_ids}")

    # Decades
    if data.get('decades') and len(data['decades']) > 0:
        filters_dict['decades'] = data['decades']

    # Get series IDs matching filters
    try:
        series_ids = filters_module.apply_filters(filters_dict)

        if not series_ids:
            return jsonify({'series': []})

        # Fetch series details
        placeholders = ','.join(['%s'] * len(series_ids))
        query = f"""
            SELECT tmdb_id, title_en, poster_path, original_language
            FROM series
            WHERE tmdb_id IN ({placeholders})
            ORDER BY popularity DESC
        """

        rows = db_utils_module.fetch_query(query, tuple(series_ids))

        series_list = []
        for row in rows:
            series_list.append({
                'tmdb_id': row[0],
                'title': row[1] or 'No Title',
                'poster': f"https://image.tmdb.org/t/p/w500{row[2]}" if row[2] else None,
                'language': row[3]
            })

        return jsonify({'series': series_list})

    except Exception as e:
        print(f"Error fetching series: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'series': [], 'error': str(e)}), 500

@app.route('/api/save-ratings', methods=['POST'])
def save_ratings():
    """Save user ratings to session"""
    data = request.json
    ratings = data.get('ratings', {})
    print(f"[DEBUG] Saving ratings to session: {ratings}")
    session['ratings'] = ratings
    print(f"[DEBUG] Session after save: {session.get('ratings', {})}")
    return jsonify({'success': True})

@app.route('/screen-3')
def screen_3():
    """Screen 3: Recommendations"""
    return render_template('recommendations.html')

@app.route('/api/get-recommendations', methods=['POST'])
def get_recommendations():
    """Get personalized recommendations based on user ratings"""
    import logic_layer.recommender as recommender_module
    import data_layer.db_utils as db_utils_module

    # Get ratings from session (saved by save-ratings endpoint)
    print(f"[DEBUG] Full session: {dict(session)}")
    ratings = session.get('ratings', {})
    print(f"[DEBUG] Ratings from session: {ratings}")

    if not ratings:
        return jsonify({'recommendations': [], 'error': 'No ratings found in session'}), 400

    # Convert ratings dict to list of tuples (tmdb_id, rating, is_anchor)
    user_ratings = []
    for tmdb_id_str, rating in ratings.items():
        tmdb_id = int(tmdb_id_str)
        # For now, no anchors - can be added later
        user_ratings.append((tmdb_id, rating, False))

    try:
        # Get 14 recommendations
        recommendations = recommender_module.get_recommendations(
            user_ratings=user_ratings,
            filters=None,  # No filters for recommendations
            top_n=14
        )

        return jsonify({'recommendations': recommendations})

    except Exception as e:
        print(f"Error getting recommendations: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'recommendations': [], 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
