from common import CommitList, Suffix, get_commits_since_last_version, get_last_version


def categorize_commits(commits: CommitList):
    major_commits = []
    minor_commits = []
    patch_commits = []
    suffix = None

    for commit in [c.lower().strip() for c in commits]:
        if "alpha:" in commit:
            suffix = "alpha"
        elif "beta:" in commit:
            suffix = "beta"

        if commit.startswith("major:"):
            major_commits.append(commit)
        elif commit.startswith("minor:"):
            minor_commits.append(commit)
        elif commit.startswith("patch:"):
            patch_commits.append(commit)

    return major_commits, minor_commits, patch_commits, suffix


def generate_release_notes(
    major_commits: CommitList,
    minor_commits: CommitList,
    patch_commits: CommitList,
    suffix: Suffix,
):
    notes = []

    if suffix:
        notes.append(
            f"**This is a {suffix} release and should not be used in production.**\n"
        )

    if major_commits:
        notes.append("### Major Changes")
        notes.extend(major_commits)

    if minor_commits:
        notes.append("### Minor Changes")
        notes.extend(minor_commits)

    if patch_commits:
        notes.append("### Patch Changes")
        notes.extend(patch_commits)

    return "\n".join(notes)


def main():
    last_version = get_last_version()
    commits = get_commits_since_last_version(last_version)
    major_commits, minor_commits, patch_commits, suffix = categorize_commits(commits)
    release_notes = generate_release_notes(
        major_commits, minor_commits, patch_commits, suffix
    )

    with open("RELEASE_NOTES.md", "w") as file:
        file.write(release_notes)


if __name__ == "__main__":
    main()
