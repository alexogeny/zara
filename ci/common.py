import re
import subprocess


def get_last_version() -> str | None:
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"], stdout=subprocess.PIPE, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_commits_since_last_version(last_version: str | None) -> list[str]:
    if last_version:
        result = subprocess.run(
            ["git", "log", f"{last_version}..HEAD", "--pretty=format:%s"],
            stdout=subprocess.PIPE,
            text=True,
        )
    else:
        # If no last version, get all commits
        result = subprocess.run(
            ["git", "log", "--pretty=format:%s"], stdout=subprocess.PIPE, text=True
        )
    return result.stdout.strip().split("\n")


def update_pyproject_toml(version):
    with open("pyproject.toml", "r") as file:
        content = file.read()

    content = re.sub(r'version = ".*"', f'version = "{version}"', content)

    with open("pyproject.toml", "w") as file:
        file.write(content)


def determine_next_version(last_version: str | None, commits: list[str]) -> str:
    if not last_version:
        last_version = "v0.1.0"

    major, minor, patch = map(int, last_version.lstrip("v").split("."))
    suffix = ""
    bump = None

    for commit in [c.lower().strip() for c in commits]:
        if commit.startswith("alpha:"):
            suffix = "alpha"
        elif commit.startswith("beta:"):
            suffix = "beta"

        if commit.startswith("major:"):
            bump = "major"
        elif commit.startswith("minor:") and bump != "major":
            bump = "minor"
        elif commit.startswith("patch:") and bump not in ["major", "minor"]:
            bump = "patch"

    if bump is None:
        return "noop"
    elif bump == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump == "minor":
        minor += 1
        patch = 0
    elif bump == "patch":
        patch += 1

    version = f"v{major}.{minor}.{patch}"
    if suffix:
        version += f"-{suffix}"

    return version
