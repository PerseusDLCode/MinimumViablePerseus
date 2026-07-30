function collectionsSearch(inputId, resultsId) {
    const input = document.getElementById(inputId);
    const results = document.getElementById(resultsId);
    const list = results ? results.querySelector('.collapse-content ul') : null;
    if (!input || !results || !list) return;

    var entries = null;

    function render(matches) {
        list.innerHTML = '';
        if (!matches.length) {
            results.classList.remove('collapse-open');
            return;
        }
        matches.slice(0, 20).forEach(function (entry) {
            const li = document.createElement('li');
            const a = document.createElement('a');
            a.href = entry.url;
            a.className = 'link block px-3 py-1.5 text-sm hover:bg-neutral-100';
            var label = entry.title + ' (' + entry.language + ')';
            if (entry.author) label += ' — ' + entry.author;
            a.textContent = label;
            li.appendChild(a);
            list.appendChild(li);
        });
        results.classList.add('collapse-open');
    }

    function search(query) {
        query = query.trim().toLowerCase();
        if (!query) {
            render([]);
            return;
        }
        const matches = entries.filter(function (entry) {
            return (
                entry.title.toLowerCase().includes(query) ||
                entry.author.toLowerCase().includes(query) ||
                entry.editors.toLowerCase().includes(query)
            );
        });
        render(matches);
    }

    input.addEventListener('input', function () {
        if (entries) {
            search(input.value);
            return;
        }
        fetch('/collections/search-index.json')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                entries = data;
                search(input.value);
            });
    });

    document.addEventListener('click', function (event) {
        if (event.target !== input) {
            results.classList.remove('collapse-open');
        }
    });
}
