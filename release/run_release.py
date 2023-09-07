import os
from utils import ReleaseHelper


def main():
    series = os.environ.get("SERIES", "jammy")
    arch = os.environ.get("ARCH", "amd64")

    channel_from = os.environ["CHANNEL_FROM"]
    channel_to = os.environ["CHANNEL_TO"]

    release_helper = ReleaseHelper(series, arch)
    if release_helper.is_release_needed(channel_from, channel_to):
        print(
            f"[{series} - {arch}][{channel_from} -> {channel_to}] Release is required, running tests..."
        )
        if not release_helper.skip_tests and not release_helper.run_integration_tests(channel_from):
            if not release_helper.force_release:
                print(
                    f"[{series} - {arch}][{channel_from} -> {channel_to}] Tests failed, stopping release process..."
                )
                return
            else:
                print(
                    f"[{series} - {arch}][{channel_from} -> {channel_to}] Tests failed, force releasing anyways..."
                )

        if not release_helper.dry_run:
            print(f"[{series} - {arch}][{channel_from} -> {channel_to}] Releasing...")
            release_helper.do_release(channel_from, channel_to)


if __name__ == "__main__":
    main()
