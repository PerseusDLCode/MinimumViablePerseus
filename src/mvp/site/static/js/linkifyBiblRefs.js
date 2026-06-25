function linkifyBiblRefs(preferredLang) {
    const refs = document.querySelectorAll('a.perseus-reference[data-ref]');
    if (!refs.length) return;

    fetch('/urn-index.json')
        .then(function (r) { return r.json(); })
        .then(function (index) {
            refs.forEach(function (el) {
                const urn = el.dataset.ref;
                if (!urn || !urn.startsWith('urn:cts:')) return;

                const parts = urn.split(':');
                if (parts.length < 5) return;

                const workUrn = parts.slice(0, 4).join(':');
                const passage = parts[4].split(".").slice(0, -1);
                const versions = index[workUrn];
                if (!versions) return;

                const prefix = versions[preferredLang] || Object.values(versions)[0];
                if (!prefix) return;

                el.href = prefix + passage + '/';
            });
        });
}
