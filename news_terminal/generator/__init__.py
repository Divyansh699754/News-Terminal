"""Generator module — builds static site and email digest."""

from news_terminal.generator.site import generate_site
from news_terminal.generator.archive import cleanup_archive
from news_terminal.generator.email_builder import build_email_html

__all__ = ["generate_site", "cleanup_archive", "build_email_html"]
