import subprocess

from .common import (
    determine_next_version,
    get_commits_since_last_version,
    get_last_version,
    update_pyproject_toml,
)


def main():
    last_version = get_last_version()
    commits = get_commits_since_last_version(last_version)
    next_version = determine_next_version(last_version, commits)

    print(next_version)
    update_pyproject_toml(next_version)

    # Commit the changes
    subprocess.run(
        [
            "git",
            "config",
            "--global",
            "user.email",
            '"6896115+alexogeny@users.noreply.github.com"',
        ]
    )
    subprocess.run(["git", "config", "--global", "user.name", '"alexogeny"'])
    subprocess.run(["git", "add", "pyproject.toml"])
    subprocess.run(["git", "commit", "-m", f"Bump version to {next_version}"])
    subprocess.run(["git", "tag", next_version])
    subprocess.run(["git", "push", "origin", "heart", "--tags"])


if __name__ == "__main__":
    main()
