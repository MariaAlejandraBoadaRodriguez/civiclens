"""Shared request dependencies."""

from fastapi import Request

from app.i18n.loader import Translator


def get_translator(request: Request) -> Translator:
    """Translator for the language negotiated by the locale middleware."""
    return getattr(request.state, "t", Translator("en"))
