from mvp.site import config


def test_old_english_corpus_label():
    assert config._CORPUS_LABELS["angLit"] == "Old English"


def test_old_english_language_label():
    assert config._LANGUAGE_LABELS["ang"] == "Old English"


def test_persian_language_label():
    assert config._LANGUAGE_LABELS["fas"] == "Persian"
