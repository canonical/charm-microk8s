import click
from utils import ReleaseHelper, Configuration

"""
The following environment variables can be set:
- Release from: FROM_CHANNEL
- Release to: TO_CHANNEL
- Architecture: ARCH
- Skip tests: SKIP_TESTS
- Tests taken from repo: REPOSITORY
- Tests taken from branch: BRANCH
- Tests run on: SERIES
- Juju controller to use: CONTROLLER
- This is a dry run: DRY_RUN

The following env must be set:

CHARMCRAFT_AUTH: Export charmstore credentials with:
  charmcraft login --ttl 8766 --export ch.cred
  export CHARMCRAFT_AUTH=$(cat ch.cred)

CONTROLLER: The juju controller the tests will run on.
"""


def echo(config, msg):
    """
    Print the msg with the prefix we want
    """
    prefix = f"[{config.series} - {config.arch}][{config.from_channel} -> {config.to_channel}]"
    click.echo(f"{prefix} {msg}")


def main():
    # Gather the test configuration from env variables
    config = Configuration()
    config.print()
    if not config.valid():
        exit(2)

    release_helper = ReleaseHelper(config.series, config.arch)

    # Check if we need to release
    if not release_helper.is_release_needed(config.from_channel, config.to_channel):
        echo(config, "Release is not required.")
        exit(0)

    # Run tests
    echo(config, "Release process started.")
    if not config.skip_tests:
        echo(
            config,
            f"Tests taken from {config.tests_repo} in branch {config.tests_branch}.",
        )

        if not release_helper.run_integration_tests(
            config.from_channel,
            config.tests_repo,
            config.tests_branch,
            config.juju_controller,
        ):
            echo(config, "Tests failed, stopping release process.")
            exit(1)

    # Release
    if config.dry_run:
        echo(config, "Dry run: releasing.")
    else:
        echo(config, "Releasing.")
        release_helper.do_release(config.from_channel, config.to_channel)


if __name__ == "__main__":
    main()
