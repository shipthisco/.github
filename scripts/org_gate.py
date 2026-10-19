"""Org-wide code gate run on every pull request. Repos without a CLAUDE.md pass untouched.

    org_gate.py <base sha>      PR_BODY in the environment holds the pull request description

Checks only lines the PR adds. Silence one line with "gate: allow <rule> -- <why>" in a comment on that line.
"""

import os
import re
import subprocess
import sys

CODE = re.compile(r"\.(py|ts|tsx|js|jsx|mjs|go|scss|css|html)$")
SKIP = re.compile(r"(^|/)(node_modules|vendor|dist|build|migrations?|generated|__snapshots__)/|\.min\.|\.spec\.|_test\.go$|(^|/)tests?/")
COMMENT = re.compile(r"^\s*(#|//|/\*|\*|<!--)")
BANNER = re.compile(r"^\s*(#|//|/\*|\*|<!--)\s*[=\-─#*~]{4,}")
NARRATION = re.compile(
    r"^\s*(#|//|/\*|\*)\s*(get|set|check|loop|iterate|call|create|update|return|initiali[sz]e|now|then|first|finally|extract|build|fetch|convert|add|remove|define|prepare|this will|here we)\b",
    re.I,
)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout


def added_lines(base):
    files, current = {}, None
    for line in git("diff", "-U0", f"{base}...HEAD").splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
            if current and (not CODE.search(current) or SKIP.search(current)):
                current = None
            if current:
                files[current] = []
        elif current and line.startswith("+") and not line.startswith("+++"):
            files[current].append(line[1:])
    return files


def main():
    if not os.path.exists("CLAUDE.md"):
        print("No CLAUDE.md in this repo, nothing to enforce.")
        return
    problems = []

    body = [line for line in re.sub(r"<!--.*?-->", "", os.environ.get("PR_BODY", ""), flags=re.S).splitlines() if line.strip()]
    if len(body) > 2:
        problems.append(f"PR description is {len(body)} lines; keep it to two (why it changed, how it was verified)")

    for path, lines in added_lines(sys.argv[1]).items():
        lines = [line for line in lines if "gate: allow" not in line]
        comments = [line for line in lines if COMMENT.match(line)]
        banners = [line for line in lines if BANNER.match(line)]
        narration = [line for line in lines if NARRATION.match(line)]
        if banners:
            problems.append(f"{path}: {len(banners)} banner/section comment(s) — delete them")
        if len(narration) >= 3:
            problems.append(f"{path}: {len(narration)} comments describe what the code does — keep only why-comments")
        if len(comments) >= 8 and len(comments) > 0.25 * len(lines):
            problems.append(f"{path}: {len(comments)} of {len(lines)} added lines are comments — comment only what the code cannot say")

    tracked = set(git("ls-files").splitlines())
    paths = tracked | {"/".join(path.split("/")[:i]) + "/" for path in tracked for i in range(1, path.count("/") + 1)}
    for token in sorted(set(re.findall(r"`([^`\s]+)`", open("CLAUDE.md").read()))):
        # Branch prefixes (feature/), placeholders (<name>, YYYY), globs, path aliases (@/) and sibling repos (../) are not repo paths.
        if re.search(r"[<*]|YYYY|^@|^\.\./", token) or re.fullmatch(r"[\w-]+/", token) or not ("/" in token or re.search(r"\.(py|ts|go|ya?ml|md|json|sh)$", token)):
            continue
        if not any(path == token or path.endswith("/" + token) for path in paths):
            problems.append(f"CLAUDE.md names {token}, which does not exist in the repo")

    print("\n".join(problems) or "Org code gate: clean")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
