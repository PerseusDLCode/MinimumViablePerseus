// Sibling editions/translations aren't inlined into each reading page (see
// mvp.site.siblings._SiblingPassage): each sibling panel lists the _text/
// fragment pages of the sibling chunk(s) aligned to this passage, in
// citation order, and they're fetched the first time the panel is opened.
(function () {
    const lang = document.querySelector('article[data-lang]')?.dataset.lang;

    function load(container) {
        const urls = JSON.parse(container.dataset.siblingFragments);
        delete container.dataset.siblingFragments;

        Promise.all(urls.map(function (url) {
            return fetch(url).then(function (r) {
                if (!r.ok) throw new Error(`${url}: ${r.status}`);
                return r.text();
            });
        }))
            .then(function (pages) {
                const parser = new DOMParser();
                container.replaceChildren();
                pages.forEach(function (html) {
                    const body = parser.parseFromString(html, 'text/html').body;
                    container.append(...body.childNodes);
                });
                if (typeof linkifyBiblRefs === 'function') {
                    linkifyBiblRefs(lang, container);
                }
            })
            .catch(function (err) {
                console.error('Could not load sibling passage', err);
                const p = document.createElement('p');
                p.className = 'italic';
                p.textContent = 'Could not load this passage; use the focus link to read it.';
                container.replaceChildren(p);
            });
    }

    document.querySelectorAll('details').forEach(function (details) {
        const container = details.querySelector(':scope > [data-sibling-fragments]');
        if (!container) return;
        details.addEventListener('toggle', function () {
            if (details.open && container.dataset.siblingFragments) load(container);
        });
    });
}());
