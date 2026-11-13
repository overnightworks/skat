from skat.web.words import SOURCE_LANGUAGE, text


def listed(names: list[str]) -> str:
    """The names joined by the German list format: „A“, „A und B“, „A, B und C“."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} und {names[-1]}"


def waiting_for(names: list[str]) -> str:
    return text(SOURCE_LANGUAGE, "table.waitingFor", names=listed(names))
