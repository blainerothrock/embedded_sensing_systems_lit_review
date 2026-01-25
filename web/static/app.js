// Shared utilities for the Literature Review web app

// Prevent double-tap zoom on mobile
document.addEventListener('touchend', (e) => {
    const now = Date.now();
    if (now - (window.lastTouchEnd || 0) < 300) {
        e.preventDefault();
    }
    window.lastTouchEnd = now;
}, { passive: false });

// Add active state feedback for touch
document.addEventListener('touchstart', (e) => {
    if (e.target.closest('.btn, .key, .decision-btn, .nav-btn, .paper-card')) {
        e.target.closest('.btn, .key, .decision-btn, .nav-btn, .paper-card').classList.add('touching');
    }
}, { passive: true });

document.addEventListener('touchend', () => {
    document.querySelectorAll('.touching').forEach(el => el.classList.remove('touching'));
}, { passive: true });

// Utility: Format dates
function formatDate(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    return date.toLocaleDateString();
}

// Utility: Debounce function
function debounce(fn, delay) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => fn.apply(this, args), delay);
    };
}
