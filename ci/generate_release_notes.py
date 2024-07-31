from typing import TypedDict

from common import CommitList, Suffix, get_commits_since_last_version, get_last_version


class CategorizedCommits(TypedDict):
    major: CommitList
    minor: CommitList
    patch: CommitList
    chore: CommitList
    build: CommitList
    docs: CommitList
    test: CommitList


def categorize_commits(commits: CommitList):
    categories: CategorizedCommits = {
        "major": [],
        "minor": [],
        "patch": [],
        "chore": [],
        "build": [],
        "docs": [],
        "test": [],
    }
    suffix = None

    for commit in [c.lower().strip() for c in commits]:
        if "alpha:" in commit:
            suffix = "alpha"
        elif "beta:" in commit:
            suffix = "beta"

        if commit.startswith("breaking:"):
            categories["major"].append(commit)
        elif commit.startswith("feat:"):
            categories["minor"].append(commit)
        elif commit.startswith("fix:"):
            categories["patch"].append(commit)
        elif commit.startswith("chore:"):
            categories["chore"].append(commit)
        elif commit.startswith("build:"):
            categories["build"].append(commit)
        elif commit.startswith("docs:"):
            categories["docs"].append(commit)
        elif commit.startswith("test:"):
            categories["test"].append(commit)

    return categories, suffix


def generate_release_notes(
    commits: CategorizedCommits,
    suffix: Suffix,
):
    notes = []

    if suffix:
        notes.append(
            f"**This is a {suffix} release and should not be used in production.**\n"
        )

    for key, values in commits:
        if values:
            notes.append(f"### {key.title()} Changes")
            notes.extend(values)

    return "\n".join(notes)


def main():
    last_version = get_last_version()
    commits = get_commits_since_last_version(last_version)
    categories, suffix = categorize_commits(commits)
    release_notes = generate_release_notes(categories, suffix)

    with open("RELEASE_NOTES.md", "w") as file:
        file.write(release_notes)


if __name__ == "__main__":
    main()
