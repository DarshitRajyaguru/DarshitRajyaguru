#!/usr/bin/env python3
"""Build a deterministic, GitHub-native activity card for the profile README.

Only public GitHub repository metadata and the public-facing 12-month contribution
collection are used. Run in GitHub Actions with the default GITHUB_TOKEN.
No third-party card hosting, pip install, or personal access token is required.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

USERNAME = os.environ.get("PROFILE_USERNAME", "DarshitRajyaguru")
DEST = Path(os.environ.get("OUTPUT_FILE", "assets/github-activity.svg"))
TOKEN = os.environ.get("GITHUB_TOKEN", "")
BASE = "https://api.github.com"


def request(url: str, data: dict | None = None) -> dict | list:
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-profile-activity-generator",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST" if payload else "GET")
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def get_public_repos() -> list[dict]:
    repos: list[dict] = []
    for page in range(1, 21):
        page_result = request(f"{BASE}/users/{USERNAME}/repos?type=owner&per_page=100&page={page}")
        if not isinstance(page_result, list):
            raise RuntimeError("GitHub repository API returned an unexpected structure")
        repos.extend(x for x in page_result if not x.get("private", False))
        if len(page_result) < 100:
            break
    return repos


def get_contributions() -> dict:
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is missing. GraphQL contribution counts require authentication.")
    response = request(
        f"{BASE}/graphql",
        {
            "query": """
              query($login: String!) {
                user(login: $login) {
                  contributionsCollection {
                    contributionCalendar { totalContributions }
                    totalCommitContributions
                    totalPullRequestContributions
                    totalIssueContributions
                  }
                }
              }
            """,
            "variables": {"login": USERNAME},
        },
    )
    if response.get("errors"):
        raise RuntimeError("GitHub GraphQL error: " + str(response["errors"])[:300])
    collection = (response.get("data") or {}).get("user")
    if not collection:
        raise RuntimeError("GitHub GraphQL returned no user")
    return collection["contributionsCollection"]


def sync_readme_cache_key(svg_content: str) -> None:
    """Change the image URL only when the underlying metrics SVG changes.

    GitHub's image proxy can cache an old SVG even when a branch file is updated.
    A content-derived URL query parameter makes the new image URL distinct,
    without changing the visual layout or continuously creating new commits.
    """
    readme_path = Path("README.md")
    if not readme_path.exists():
        return
    readme = readme_path.read_text(encoding="utf-8")
    url = (
        f"https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/"
        "main/assets/github-activity.svg"
    )
    pattern = re.escape(url) + r"(?:\\?v=[0-9a-f]{12})?"
    # Each image version is stable until the underlying metrics change.
    version = hashlib.sha256(svg_content.encode("utf-8")).hexdigest()[:12]
    updated, matches = re.subn(pattern, lambda _: f"{url}?v={version}", readme)
    if matches != 1:
        raise RuntimeError(
            "Expected a single GitHub activity image URL in README.md; "
            f"found {matches}. Please check the image reference."
        )
    if updated != readme:
        readme_path.write_text(updated, encoding="utf-8")
        print(f"Updated README.md activity image cache key: {version}")


def metric_card(x: int, value: str, label: str, note: str, accent: str) -> str:
    e = html.escape
    return f'''  <g transform="translate({x} 120)">
    <rect x="0" y="0" width="214" height="132" rx="15" fill="#111F36" stroke="#294260" stroke-width="1"/>
    <rect x="16" y="19" width="4" height="24" rx="2" fill="{accent}"/>
    <text x="31" y="49" fill="#F3F7FF" font-size="35" font-weight="800">{e(value)}</text>
    <text x="16" y="81" fill="#B8CADF" font-size="14" font-weight="700">{e(label)}</text>
    <text x="16" y="104" fill="#7E9AB8" font-size="11">{e(note)}</text>
  </g>'''


def svg(data: dict) -> str:
    contributions = data["contributions"]
    cards = [
        ("12-mo contributions", "GitHub contribution graph", contributions["contributionCalendar"]["totalContributions"], "#54B6FF"),
        ("Commits", "Past 12 months", contributions["totalCommitContributions"], "#70D6BA"),
        ("Pull requests", "Past 12 months", contributions["totalPullRequestContributions"], "#BFA4FF"),
        ("Public repositories", "Currently accessible", data["repos"], "#F5B36A"),
        ("Stars received", "Across public repositories", data["stars"], "#FFCF74"),
    ]
    marks = "\n".join(
        metric_card(30 + i * 232, f"{value:,}", label, note, color)
        for i, (label, note, value, color) in enumerate(cards)
    )
    # Deliberately omit time stamps: unchanged data means no new Git commit on each poll.
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1220" height="307" viewBox="0 0 1220 307" role="img" aria-label="GitHub activity statistics for {html.escape(USERNAME)}">
  <defs>
    <linearGradient id="background" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0A1425"/>
      <stop offset="1" stop-color="#111E33"/>
    </linearGradient>
    <linearGradient id="stripe" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#55A3FF"/>
      <stop offset="1" stop-color="#43D9BF"/>
    </linearGradient>
  </defs>
  <rect x="1" y="1" width="1218" height="305" rx="20" fill="url(#background)" stroke="#314864"/>
  <rect x="30" y="28" width="5" height="34" rx="2.5" fill="url(#stripe)"/>
  <text x="48" y="49" font-family="Arial,Helvetica,sans-serif" font-size="25" font-weight="800" fill="#FFFFFF">GitHub activity</text>
  <text x="48" y="76" font-family="Arial,Helvetica,sans-serif" font-size="13" fill="#9AB1CD">Public repository metrics · rolling 12-month contributions</text>
  <rect x="1005" y="34" width="182" height="31" rx="15.5" fill="#133C3F" stroke="#26746B"/>
  <circle cx="1021" cy="49.5" r="4" fill="#56E2BD"/>
  <text x="1033" y="54" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="12" fill="#91F2D5">AUTO-UPDATED</text>
  <g font-family="Arial,Helvetica,sans-serif">
{marks}
  </g>
  <text x="31" y="279" font-family="Arial,Helvetica,sans-serif" font-size="12" fill="#8DA5C1">Source: GitHub API · Rebuilt on profile pushes and scheduled checks · Repository and contribution counts may differ from external cards</text>
</svg>
'''


def main() -> None:
    try:
        repos = get_public_repos()
        contributions = get_contributions()
        output = svg({
            "repos": len(repos),
            "stars": sum(int(r.get("stargazers_count") or 0) for r in repos),
            "contributions": contributions,
        })
    except (urllib.error.URLError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(f"Cannot refresh activity metrics: {exc}", file=sys.stderr)
        sys.exit(1)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists() and DEST.read_text(encoding="utf-8") == output:
        sync_readme_cache_key(output)
        print("GitHub activity metrics have not changed; no SVG update necessary.")
        return
    DEST.write_text(output, encoding="utf-8")
    sync_readme_cache_key(output)
    print(f"Updated {DEST}: public repos={len(repos)}, stars={sum(int(r.get('stargazers_count') or 0) for r in repos)}, contributions={contributions['contributionCalendar']['totalContributions']}")


if __name__ == "__main__":
    main()