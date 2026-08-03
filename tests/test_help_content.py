"""Validace struktury obsahu nápovědy (`stahovac/help_content.py`)."""

from stahovac.help_content import HELP_SECTIONS, HelpCode, HelpQA, HelpText


def test_has_sections():
    assert len(HELP_SECTIONS) >= 3


def test_text_sections_have_title_and_items():
    for section in HELP_SECTIONS:
        if isinstance(section, HelpText):
            assert section.title.strip(), "HelpText sekce bez titulku"
            assert section.items, "HelpText sekce bez obsahu"
            assert any(item.strip() for item in section.items), f"HelpText sekce bez textu: {section.title!r}"


def test_qa_sections_have_title_and_pairs():
    for section in HELP_SECTIONS:
        if isinstance(section, HelpQA):
            assert section.title.strip(), "HelpQA sekce bez titulku"
            assert section.items, "HelpQA sekce bez otázek"
            for question, answer in section.items:
                assert question.strip(), "prázdná otázka"
                assert answer.strip(), f"prázdná odpověď na {question!r}"


def test_code_blocks_have_lines():
    for section in HELP_SECTIONS:
        if isinstance(section, HelpCode):
            assert section.lines, "prázdný blok kódu"


def test_unique_titles():
    seen: set[str] = set()
    for section in HELP_SECTIONS:
        title = getattr(section, "title", "")
        if title.strip():
            assert title not in seen, f"duplicitní titulek: {title!r}"
            seen.add(title)


def test_no_duplicate_questions():
    seen: set[str] = set()
    for section in HELP_SECTIONS:
        if isinstance(section, HelpQA):
            for question, _ in section.items:
                assert question not in seen, f"duplicitní otázka: {question!r}"
                seen.add(question)
