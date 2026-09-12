/**
 * Series Architect - Recommendations Page
 */

// State
const state = {
    allRecommendations: []  // All 14 recommendations
};

// Initialize on load
document.addEventListener('DOMContentLoaded', function() {
    loadRecommendations();
});

/**
 * Load recommendations from backend
 */
function loadRecommendations() {
    // Fetch recommendations - ratings already in session from previous page
    fetch('/api/get-recommendations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})  // Ratings already in Flask session
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert('Error: ' + data.error);
            window.location.href = '/';
            return;
        }

        state.allRecommendations = data.recommendations;

        // Hide loading, show grid
        document.getElementById('loading').style.display = 'none';
        document.getElementById('recommendations-grid').style.display = 'grid';

        // Display first 6 recommendations
        displayInitialRecommendations();
    })
    .catch(error => {
        console.error('Error loading recommendations:', error);
        alert('Failed to load recommendations. Please try again.');
        window.location.href = '/';
    });
}

/**
 * Display all 14 recommendations
 */
function displayInitialRecommendations() {
    const grid = document.getElementById('recommendations-grid');
    grid.innerHTML = '';

    // Show all recommendations (up to 14)
    state.allRecommendations.forEach((series, index) => {
        const card = createRecommendationCard(series, index);
        grid.appendChild(card);
    });
}

/**
 * Create a recommendation card
 */
function createRecommendationCard(series, index) {
    const card = document.createElement('div');
    card.className = 'rec-card';
    card.dataset.index = index;
    card.onclick = () => openModal(series);

    // Poster
    const posterContainer = document.createElement('div');
    posterContainer.className = 'poster-container';

    if (series.poster_path) {
        const img = document.createElement('img');
        img.src = `https://image.tmdb.org/t/p/w500${series.poster_path}`;
        img.alt = series.title_en;
        posterContainer.appendChild(img);
    } else {
        const placeholder = document.createElement('div');
        placeholder.className = 'poster-placeholder';
        placeholder.textContent = 'No Image';
        posterContainer.appendChild(placeholder);
    }

    // Title
    const title = document.createElement('div');
    title.className = 'rec-card-title';
    title.textContent = series.title_en || series.title_he || 'Unknown Title';

    // Genres
    const genres = document.createElement('div');
    genres.className = 'rec-card-genres';
    genres.textContent = series.genres ? series.genres.slice(0, 2).join(', ') : '';

    // Assemble
    card.appendChild(posterContainer);
    card.appendChild(title);
    card.appendChild(genres);

    return card;
}

/**
 * Open modal with series details
 */
function openModal(series) {
    const modal = document.getElementById('series-modal');

    // Populate modal
    document.getElementById('modal-title').textContent = series.title_en || series.title_he;

    // Poster
    const posterImg = document.getElementById('modal-poster-img');
    if (series.poster_path) {
        posterImg.src = `https://image.tmdb.org/t/p/w500${series.poster_path}`;
        posterImg.alt = series.title_en;
    } else {
        posterImg.src = '';
        posterImg.alt = 'No image';
    }

        // Rating (real TMDB vote average)
    document.getElementById('modal-rating').textContent =
        series.vote_average ? `⭐ ${series.vote_average.toFixed(1)}/10` : 'No rating yet';

    // Genres
    document.getElementById('modal-genres').textContent =
        series.genres ? series.genres.join(' • ') : '';

    // Years
    const startYear = series.first_air_date ? series.first_air_date.substring(0, 4) : '?';
    //const endYear = series.last_air_date ? series.last_air_date.substring(0, 4) : 'Present';
    document.getElementById('modal-years').textContent =
        `📅 ${startYear}`;

    // Status
    document.getElementById('modal-status').textContent =
        `🏁 ${series.status || 'Unknown'} • ${series.number_of_seasons || '?'} Seasons`;

    // Country
    document.getElementById('modal-country').textContent =
        `🌍 ${series.origin_country || 'Unknown'}`;

    // Streaming (placeholder - would need provider data)
    document.getElementById('modal-streaming').textContent = '📺 Check availability';

    // Overview
    document.getElementById('modal-overview-text').textContent =
        series.overview || 'No overview available.';

    // Show modal
    modal.classList.add('active');

    // Close on overlay click
    const overlay = modal.querySelector('.modal-overlay');
    overlay.onclick = closeModal;
}

/**
 * Close modal
 */
function closeModal() {
    const modal = document.getElementById('series-modal');
    modal.classList.remove('active');
}

// Close modal on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeModal();
    }
});