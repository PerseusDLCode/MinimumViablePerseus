function linkifyBiblRefs(preferredLang) {
    const refs = document.querySelectorAll('a.perseus-reference[data-ref]');
    if (!refs.length) return;

    // refs need to be shortened to work-level URN, then matched against
    // every edition urn-index.json has for that work. A single available
    // edition links directly; more than one populates the ref's dropdown
    // (see text_elements/ref.html.jinja, bibl.html.jinja) source-language-
    // first, so the reader picks the edition instead of one being silently
    // chosen for them.
    fetch('/urn-index.json')
        .then(function (r) { return r.json(); })
        .then(function (index) {
            refs.forEach(function (el) {
                const urn = el.dataset.ref;
                if (!urn || !urn.startsWith('urn:cts:')) return;

                const parts = urn.split(':');
                if (parts.length < 5) return;

                const workUrn = parts.slice(0, 4).join(':');
                const passage = parts[4].split('.').slice(0).join('.');
                const versions = index[workUrn];
                if (!versions || !versions.length) return;

                const sorted = versions.slice().sort(function (a, b) {
                    if (a.language === preferredLang) return -1;
                    if (b.language === preferredLang) return 1;
                    return a.language.localeCompare(b.language);
                });

                function hrefFor(version) {
                    const rk = version.route_kwargs;
                    return (
                        '/urn:cts:' + rk.corpus + ':' + rk.textgroup + '.' + rk.work +
                        '.' + rk.version + ':' + passage + '/'
                    );
                }

                const menu = el.parentElement && el.parentElement.querySelector('.perseus-reference-versions');
                if (!menu) return;

                sorted.forEach(function (version) {
                    const li = document.createElement('li');
                    const a = document.createElement('a');
                    a.href = hrefFor(version);
                    a.textContent = `${version.label} (${version.language_label || version.language})`
                    li.appendChild(a);
                    menu.appendChild(li);
                });
            });
        });
}
