from typing import TypedDict

from common import CommitList, Suffix, get_commits_since_last_version, get_last_version


class CategorizedCommits(TypedDict):
    breaking_changes: CommitList
    features: CommitList
    fixes: CommitList
    chores: CommitList
    build: CommitList
    docs: CommitList
    test: CommitList
    style: CommitList
    refactor: CommitList
    perf: CommitList
    ci: CommitList
    revert: CommitList


def categorize_commits(commits: CommitList):
    categories: CategorizedCommits = {
        "breaking_changes": [],
        "features": [],
        "fixes": [],
        "chores": [],
        "build": [],
        "docs": [],
        "test": [],
        "style": [],
        "refactor": [],
        "perf": [],
        "ci": [],
        "revert": [],
    }
    suffix = None

    for commit in [c.lower().strip() for c in commits]:
        if ":" not in commit:  # ignore commits not matching the format
            continue
        prefix, message = commit.split(":", 1)
        if prefix == "alpha":
            suffix = "alpha"
        elif prefix == "beta":
            suffix = "beta"

        if prefix == "breaking":
            categories["breaking_changes"].append(message)
        elif prefix == "feat":
            categories["features"].append(message)
        elif prefix == "fix":
            categories["fixes"].append(message)
        elif prefix == "chore":
            categories["chores"].append(message)
        elif prefix == "build":
            categories["build"].append(message)
        elif prefix == "docs":
            categories["docs"].append(message)
        elif prefix == "test":
            categories["test"].append(message)
        elif prefix == "style":
            categories["style"].append(message)
        elif prefix == "refactor":
            categories["refactor"].append(message)
        elif prefix == "perf":
            categories["perf"].append(message)
        elif prefix == "ci":
            categories["ci"].append(message)
        elif prefix == "revert":
            categories["revert"].append(message)

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
