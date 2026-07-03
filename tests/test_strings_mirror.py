"""
Guards the language toggle in src/strings.py: the fully commented ENGLISH
MIRROR block must stay valid Python and define exactly the same public names
as the active German block — otherwise a forker's language switch breaks.
"""

import pathlib

import src.strings as strings

_SOURCE = pathlib.Path(strings.__file__).read_text(encoding="utf-8")
_MIRROR_BANNER = "# # ENGLISH MIRROR"


def _english_namespace() -> dict:
    """Uncomment the English mirror block and exec it into a fresh namespace."""
    start = _SOURCE.index(_MIRROR_BANNER)
    lines = []
    for line in _SOURCE[start:].splitlines():
        if line.startswith("# "):
            lines.append(line[2:])
        elif line.rstrip() == "#":
            lines.append("")
        else:  # blank lines between commented stanzas
            lines.append(line)
    namespace: dict = {}
    exec(compile("\n".join(lines), "<english-mirror>", "exec"), namespace)  # noqa: S102
    return namespace


def _public_names(namespace) -> set[str]:
    return {n for n in namespace if n.isupper() and not n.startswith("_")}


def test_english_mirror_defines_the_same_names_as_german():
    german = _public_names(vars(strings))
    english = _public_names(_english_namespace())
    assert german - english == set(), f"missing in English mirror: {german - english}"
    assert english - german == set(), f"only in English mirror: {english - german}"


def test_english_mirror_templates_keep_the_same_placeholders():
    """A translated template must keep the exact {placeholders} the code fills."""
    import string as stdlib_string

    def placeholders(template: str) -> set[str]:
        return {
            field
            for _, field, _, _ in stdlib_string.Formatter().parse(template)
            if field
        }

    english = _english_namespace()
    for name, german_value in vars(strings).items():
        if name.isupper() and isinstance(german_value, str) and name in english:
            assert placeholders(german_value) == placeholders(english[name]), (
                f"{name}: placeholder mismatch between German and English mirror"
            )
