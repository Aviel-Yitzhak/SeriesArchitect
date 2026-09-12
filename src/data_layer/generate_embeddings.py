from sentence_transformers import SentenceTransformer
from db_utils import fetch_query, execute_query

print("Loading multilingual embedding model (first run downloads it, ~470MB)...")
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')


def build_text(title, overview, genres, keywords):
    parts = [title or '', overview or '', genres or '', keywords or '']
    return '. '.join(p for p in parts if p.strip())


def generate_all_embeddings():
    print("Fetching all series with genres and keywords in one query...")

    query = """
        SELECT s.tmdb_id, s.title_en, s.overview,
               COALESCE(string_agg(DISTINCT g.genre_name, ', '), '') AS genres,
               COALESCE(string_agg(DISTINCT k.name, ', '), '') AS keywords
        FROM series s
        LEFT JOIN series_genres sg ON s.tmdb_id = sg.tmdb_id
        LEFT JOIN genres g ON sg.genre_id = g.genre_id
        LEFT JOIN series_keywords sk ON s.tmdb_id = sk.tmdb_id
        LEFT JOIN keywords k ON sk.keyword_id = k.keyword_id
        GROUP BY s.tmdb_id, s.title_en, s.overview
    """
    rows = fetch_query(query)
    total = len(rows)
    print(f"Found {total} series. Computing embeddings...")

    for i, (tmdb_id, title_en, overview, genres, keywords) in enumerate(rows):
        text = build_text(title_en, overview, genres, keywords)

        if not text.strip():
            print(f"Skipping {tmdb_id} - no text available")
            continue

        embedding = model.encode(text).tolist()
        embedding_str = '[' + ','.join(map(str, embedding)) + ']'

        execute_query(
            "UPDATE series SET embedding = %s::vector WHERE tmdb_id = %s",
            (embedding_str, tmdb_id),
            fetch=False
        )

        if i % 50 == 0:
            print(f"Processed {i}/{total}...")

    print("Done! All embeddings computed and saved.")


if __name__ == "__main__":
    generate_all_embeddings()