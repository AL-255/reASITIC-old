"""Sphinx configuration for the reASITIC documentation site."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

# -- Path setup --------------------------------------------------------------

_DOCS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _DOCS_DIR.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# -- Project information -----------------------------------------------------

project = "reASITIC"
author = "AL-255"
copyright = f"{datetime.now():%Y}, {author}"

try:
    release = _pkg_version("reASITIC")
except PackageNotFoundError:
    # Fall back to the source-of-truth file when running outside an install
    _ns: dict[str, str] = {}
    exec((_REPO_ROOT / "src" / "reasitic" / "_version.py").read_text(), _ns)
    release = _ns["__version__"]
version = ".".join(release.split(".")[:2])

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.mathjax",
    "sphinx.ext.doctest",
    "sphinx.ext.todo",
    "myst_parser",
    "sphinx_copybutton",
]

# sphinx-copybutton: only copy actual command, strip prompts
copybutton_prompt_text = r">>> |\.\.\. |\$ |reASITIC> "
copybutton_prompt_is_regexp = True

# myst-parser: enable extensions we use in the .md files we include
myst_enable_extensions = [
    "deflist",
    "colon_fence",
    "smartquotes",
    "tasklist",
]
myst_heading_anchors = 3

# Several .md files we ``include`` (FAQ, TUTORIAL, MAPPING…) link to each
# other with relative paths like ``./TUTORIAL.md``. In docs/ we re-host
# them under different filenames, so these resolve at runtime via the
# parent navigation rather than via direct xrefs. Suppress the noise.
suppress_warnings = ["myst.xref_missing"]

# AutoSummary: generate stub pages for every public symbol
autosummary_generate = True
autosummary_ignore_module_all = False

# AutoDoc: order members by source code, document class + __init__ together
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"
autodoc_typehints_format = "short"
autodoc_class_signature = "separated"

# Napoleon: numpy + google style docstrings (we use a hybrid in places)
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_use_admonition_for_examples = True
napoleon_use_rtype = False

# Intersphinx links to the libraries we depend on
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "scipy": ("https://docs.scipy.org/doc/scipy/", None),
    "matplotlib": ("https://matplotlib.org/stable/", None),
}

# Rendering
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Allow Markdown alongside reStructuredText
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
master_doc = "index"

# Cross-references
default_role = "py:obj"
nitpicky = False  # set to True locally to hunt for broken xrefs

# -- Options for HTML output -------------------------------------------------

html_theme = "furo"
html_title = f"reASITIC {release}"
html_static_path = ["_static"]
html_css_files: list[str] = []

html_theme_options = {
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    "source_repository": "https://github.com/AL-255/reASITIC",
    "source_branch": "main",
    "source_directory": "docs/",
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/AL-255/reASITIC",
            "html": (
                '<svg stroke="currentColor" fill="currentColor" '
                'stroke-width="0" viewBox="0 0 16 16">'
                '<path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 '
                "3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 "
                "0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-"
                "0.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 "
                "1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 "
                "0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 "
                "0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 "
                "0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 "
                "1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 "
                "0 3.07-1.87 3.75-3.65 "
                "3.95.29.25.54.73.54 1.48 0 1.07-.01 "
                "1.93-.01 2.2 0 .21.15.46.55.38A8.012 8.012 "
                '0 0016 8c0-4.42-3.58-8-8-8z"></path></svg>'
            ),
            "class": "",
        },
    ],
}

# -- Options for the LaTeX/PDF builder ---------------------------------------

latex_elements: dict[str, str] = {
    "preamble": r"\usepackage{amsmath}\usepackage{amssymb}",
}

# -- Misc --------------------------------------------------------------------

# Treat warnings as errors when SPHINXOPTS=-W is passed (CI does this).
# Allow nitpicky overrides here when needed:
nitpick_ignore: list[tuple[str, str]] = []

# Make sure Sphinx finds the `napoleon` example directives during autosummary
# regeneration — set MPLBACKEND so any matplotlib import inside an autodoc'd
# module never tries to open a display.
os.environ.setdefault("MPLBACKEND", "Agg")
