// This fragment is shared across every chunk of a work, so there's no
// single "current" item at render time. The parent page passes the
// current urn as a data attribute (not a URL fragment, which was causing
// the outer page to jump on load/navigation) and we open the right
// <details> here.
(function () {
    const currentUrn = window.frameElement && window.frameElement.dataset.currentUrn;
    if (!currentUrn) return;

    const target = document.getElementById(currentUrn);
    if (!target) return;

    target.closest('li').classList.add('menu-active');

    let ancestor = target.closest('details');
    while (ancestor) {
        ancestor.open = true;
        ancestor = ancestor.parentElement && ancestor.parentElement.closest('details');
    }

    // Not scrollIntoView(): per spec it's allowed to scroll ancestor
    // scrolling boxes (including the parent frame's document) to bring
    // the target into view, and overscroll-behavior only blocks scroll
    // *chaining* from wheel/touch input, not this. Scroll only this
    // window's own viewport instead.
    const rect = target.getBoundingClientRect();
    const targetCenter = rect.top + rect.height / 2;
    const viewportCenter = window.innerHeight / 2;
    window.scrollBy({ top: targetCenter - viewportCenter });
}());
