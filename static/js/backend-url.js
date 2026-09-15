// Backend URL Configuration
// This file sets window.BACKEND_URL for the main config module (static/js/config.js)
// Auto-generated during Firebase deployment from BACKEND_URL in .env
// For local development, detect if we're on localhost:3000 and point to backend on 8080
if (window.location.hostname === 'localhost' && window.location.port === '3000') {
    window.BACKEND_URL = 'http://localhost:8080';
} else if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    window.BACKEND_URL = 'http://localhost:8080';
} else {
    // Production frontend should target the deployed backend explicitly.
    window.BACKEND_URL = window.BACKEND_URL || 'https://nutrifaq-api-chhpeha3h9ehegft.canadacentral-01.azurewebsites.net';
}

window.BACKEND_URL = 'https://nutrifaq-api-chhpeha3h9ehegft.canadacentral-01.azurewebsites.net';