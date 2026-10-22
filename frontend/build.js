// Runs during the Vercel build: writes config.js with the backend URL from VITE_API_BASE.
const fs = require('fs');
const path = require('path');

const apiBase = (process.env.VITE_API_BASE || 'http://localhost:8001').replace(/\/+$/, '');
fs.writeFileSync(path.join(__dirname, 'config.js'), `window.VITE_API_BASE = ${JSON.stringify(apiBase)};\n`);
console.log(`Generated config.js with VITE_API_BASE: ${apiBase}`);
