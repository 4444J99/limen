"""Harmless production canary: Chat can improve this receipt label formatter."""


def receipt_label(repository: str, head: str) -> str:
    return f"{repository}@{head[:12]}"
