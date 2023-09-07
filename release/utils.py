from typing import Any, Dict, Callable
from craft_store import StoreClient, endpoints
from craft_store.auth import Auth
from craft_store.models.release_request_model import ReleaseRequestModel
from craft_store.models.charm_list_releases_model import (
    ListReleasesModel,
)
import pytest
import os
from juju.utils import get_series_version
from pytest import ExitCode


class CharmhubHelper:
    def with_store_client(func: Callable[[StoreClient], Any]):
        def _run_with_store_client():
            auth = Auth("microk8s-ci", "api.charmhub.io", environment_auth="CHARMCRAFT_AUTH")
            store_client = StoreClient(
                application_name="microk8s-ci",
                base_url="https://api.charmhub.io",
                storage_base_url="https://storage.snapcraftcontent.com",
                endpoints=endpoints.CHARMHUB,
                user_agent="microk8s-ci",
                environment_auth="CHARMCRAFT_AUTH",
            )
            return func(store_client)

        return _run_with_store_client

    @with_store_client
    def generate_revision_map(
        store_client: StoreClient,
    ) -> Dict[str, Dict[str, Dict[str, int]]]:
        releases: ListReleasesModel = store_client.get_list_releases(name="microk8s")
        revmap = {}
        for channel_map in releases.channel_map:
            if channel_map.channel not in revmap:
                revmap[channel_map.channel] = {}
            if channel_map.base.channel not in revmap[channel_map.channel]:
                revmap[channel_map.channel][channel_map.base.channel] = {}

            revmap[channel_map.channel][channel_map.base.channel][
                channel_map.base.architecture
            ] = channel_map.revision

        return revmap


class ReleaseHelper:
    def __init__(
        self,
        series: str,
        arch: str,
        force_release: bool = False,
        dry_run: bool = True,
        skip_tests: bool = False,
    ) -> None:
        self.arch = arch
        self.series = series
        self.version = get_series_version(self.series)
        self.force_release = force_release
        self.dry_run = dry_run
        self.skip_tests = skip_tests
        self.revision_map: Dict[
            str, Dict[str, Dict[str, int]]
        ] = CharmhubHelper.generate_revision_map()

    def get_channel_revision(self, channel):
        if channel not in self.revision_map:
            raise ValueError("This channel does not exist!")

        if self.version not in self.revision_map[channel]:
            raise ValueError("This base version is not available for the channel!")

        if self.arch not in self.revision_map[channel][self.version]:
            raise ValueError("This arch is not available for the channel and base version!")

        return self.revision_map[channel][self.version][self.arch]

    def is_release_needed(self, channel_from: str, channel_to: str) -> bool:
        if channel_from not in self.revision_map:
            raise ValueError("Can not promote a non-existing channel!")

        if self.force_release:
            return True

        # We should promote if the channel does not exist.
        if channel_to not in self.revision_map:
            return True

        return self.get_channel_revision(channel_from) > self.get_channel_revision(channel_to)

    def run_integration_tests(self, channel) -> bool:
        os.environ["MK8S_SERIES"] = self.series
        os.environ["MK8S_CHARM"] = "ch:microk8s"
        os.environ["MK8S_CHARM_CHANNEL"] = channel
        os.environ["MK8S_CHARM_REVISION"] = self.get_channel_revision(channel)

        retcode: ExitCode = pytest.main(
            [
                "-v",
                "-s",
                "--tb",
                "native",
                "--log-file-level",
                "DEBUG",
                "--log-file",
                "pytest.log",
                "--log-cli-level",
                "INFO",
                "--disable-warnings",
                "--model",
                "testing",
                "charm-microk8s/tests/integration",
            ]
        )

        if not retcode == ExitCode.OK:
            return False

        return True

    @CharmhubHelper.with_store_client
    def do_release(self, store_client: StoreClient, channel_from, channel_to):
        store_client.release(
            "microk8s",
            release_request=ReleaseRequestModel(
                channel=channel_to, revision=self.get_channel_revision(channel_from)
            ),
        )
