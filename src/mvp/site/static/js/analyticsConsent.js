// GDPR consent toast for Google Analytics (#analytics-consent in
// base.html.jinja). Nothing is fetched from Google until the visitor
// accepts: gtag.js is injected only once consent is "granted". The choice is
// remembered in localStorage, and the "Cookie preferences" footer button
// reopens the toast so consent can be withdrawn as easily as it was given.
//
// The measurement ID comes from this script tag's data-measurement-id
// (base.html.jinja).

const STORAGE_KEY = 'perseus-analytics-consent';
const measurementId = document.querySelector('script[data-measurement-id]')?.dataset.measurementId ?? '';

function readConsent() {
    try {
        return localStorage.getItem(STORAGE_KEY);
    } catch {
        return null;
    }
}

function writeConsent(value) {
    try {
        localStorage.setItem(STORAGE_KEY, value);
    } catch {
        // Storage blocked (private mode etc.): the choice holds for this page only.
    }
}

function loadAnalytics() {
    if (!measurementId || window.gtag) return;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag() { window.dataLayer.push(arguments); };
    window.gtag('js', new Date());
    window.gtag('config', measurementId, { anonymize_ip: true });
    const script = document.createElement('script');
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
    document.head.appendChild(script);
}

// GA sets _ga and _ga_<container> on the registrable domain, so try each
// parent domain as well as the bare host.
function clearAnalyticsCookies() {
    const names = document.cookie.split(';')
        .map((c) => c.split('=')[0].trim())
        .filter((name) => name === '_ga' || name.startsWith('_ga_') || name === '_gid');
    const parts = window.location.hostname.split('.');
    const domains = [''];
    for (let i = 0; i < parts.length - 1; i++) {
        domains.push(`; domain=.${parts.slice(i).join('.')}`);
    }
    for (const name of names) {
        for (const domain of domains) {
            document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/${domain}`;
        }
    }
}

const toast = document.getElementById('analytics-consent');

function choose(value) {
    const previous = readConsent();
    writeConsent(value);
    toast.classList.add('hidden');
    if (value === 'granted') {
        loadAnalytics();
    } else if (previous === 'granted') {
        // gtag.js may already be running on this page; a reload is the only
        // way to be sure it stops.
        clearAnalyticsCookies();
        window.location.reload();
    }
}

for (const button of document.querySelectorAll('[data-analytics-consent]')) {
    button.addEventListener('click', () => choose(button.dataset.analyticsConsent));
}
for (const button of document.querySelectorAll('[data-analytics-consent-open]')) {
    button.addEventListener('click', () => toast.classList.remove('hidden'));
}

const consent = readConsent();
if (consent === 'granted') {
    loadAnalytics();
} else if (consent === null) {
    toast.classList.remove('hidden');
}
