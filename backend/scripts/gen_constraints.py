"""Generate `backend/constraints.txt` from the installed dependency closure.

Pins the exact versions this project's requirements resolve to, so CI, a local
virtualenv and the Docker image install the same bytes. Constraints never add
packages — they only clamp versions of packages that are already required.

Usage:
    python scripts/gen_constraints.py          # refresh after an intentional upgrade
    pip install -r requirements.txt -r requirements-dev.txt -c constraints.txt
"""

import importlib.metadata as md
import pathlib
import re

# Direct requirements (extras are listed separately because metadata marks them
# optional). Keep this list in sync with requirements*.txt.
ROOTS = [
    "Django",
    "django-ninja",
    "django-cors-headers",
    "httpx",
    "beautifulsoup4",
    "python-dotenv",
    "PyJWT",
    "psycopg",
    "psycopg-binary",
    "sentry-sdk",
    "django-otp",
    "gunicorn",
    "django-stubs",
    "pip-audit",
    "ruff",
    "pyright",
]

HEADER = [
    "# Pinned dependency closure for reproducible CI, local and Docker installs.",
    "# Regenerate after an intentional upgrade: python scripts/gen_constraints.py",
    "# Install with: pip install -r requirements.txt -r requirements-dev.txt -c constraints.txt",
    "",
]


def _name(requirement: str) -> str:
    base = requirement.split(";")[0].strip().split("[")[0]
    return re.split(r"[ <>=!~]", base, maxsplit=1)[0]


def _walk(name: str, found: dict[str, tuple[str, str]]) -> None:
    key = name.lower().replace("_", "-")
    if key in found:
        return
    try:
        dist = md.distribution(name)
    except md.PackageNotFoundError:
        return
    found[key] = (dist.metadata["Name"], dist.version)
    for requirement in dist.requires or []:
        dependency = _name(requirement)
        if dependency:
            _walk(dependency, found)


def main() -> None:
    found: dict[str, tuple[str, str]] = {}
    for root in ROOTS:
        _walk(root, found)

    lines = [f"{name}=={version}" for name, version in sorted(found.values(), key=lambda x: x[0].lower())]
    output = pathlib.Path(__file__).resolve().parent.parent / "constraints.txt"
    output.write_text("\n".join(HEADER + lines) + "\n", encoding="utf-8")
    print(f"Wrote {output} ({len(lines)} pins)")


if __name__ == "__main__":
    main()
