import click
from typing import Any, Dict, Callable
from craft_store import StoreClient, endpoints
from craft_store.auth import Auth
from craft_store.models.release_request_model import ReleaseRequestModel
from craft_store.models.charm_list_releases_model import (
    ListReleasesModel,
)
import os
from juju.utils import get_series_version

import sh
import shlex
from pathlib import Path


class CharmhubHelper:
    def get_store_client():
        auth = Auth(
            "microk8s-ci", "api.charmhub.io", environment_auth="CHARMCRAFT_AUTH"
        )
        store_client = StoreClient(
            application_name="microk8s-ci",
            base_url="https://api.charmhub.io",
            storage_base_url="https://storage.snapcraftcontent.com",
            endpoints=endpoints.CHARMHUB,
            user_agent="microk8s-ci",
            environment_auth="CHARMCRAFT_AUTH",
        )
        return store_client

    def with_store_client(func: Callable[[StoreClient], Any]):
        def _run_with_store_client():
            store_client = CharmhubHelper.get_store_client()
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
    ) -> None:
        self.arch = arch
        self.series = series
        self.version = get_series_version(self.series)
        self.revision_map: Dict[
            str, Dict[str, Dict[str, int]]
        ] = CharmhubHelper.generate_revision_map()

    def get_channel_revision(self, channel):
        if channel not in self.revision_map:
            raise ValueError("This channel does not exist!")

        if self.version not in self.revision_map[channel]:
            raise ValueError("This base version is not available for the channel!")

        if self.arch not in self.revision_map[channel][self.version]:
            raise ValueError(
                "This arch is not available for the channel and base version!"
            )

        return self.revision_map[channel][self.version][self.arch]

    def is_release_needed(self, from_channel: str, to_channel: str) -> bool:
        if from_channel not in self.revision_map:
            raise ValueError("Can not promote a non-existing channel!")

        # We should promote if the channel does not exist.
        if to_channel not in self.revision_map:
            return True

        return self.get_channel_revision(from_channel) > self.get_channel_revision(
            to_channel
        )

    def _remove_microk8s_directory(self):
        cmd = "rm -rf charm-microk8s"
        self._run_cmd(cmd)

    def _run_cmd(self, cmd, _cwd=Path(), _env=os.environ.copy()):
        prog, *args = shlex.split(cmd)
        local_run = getattr(sh, prog).bake(
            *args, _iter=True, _err_to_out=True, _env=_env, _cwd=_cwd
        )
        print(f"Executing: {cmd}")
        for line in local_run():
            print(line.strip())

    def _clone_repo(self, repo):
        cmd = f"git clone {repo}"
        self._run_cmd(cmd)

    def _checkout_branch(self, branch):
        cmd = f"git checkout {branch}"
        self._run_cmd(cmd, _cwd=Path("charm-microk8s"))

    def _juju_switch(self, controller):
        cmd = f"juju switch {controller}"
        self._run_cmd(cmd)

    def run_integration_tests(self, channel, repo, branch, controller) -> bool:
        self._remove_microk8s_directory()
        self._clone_repo(repo)
        self._checkout_branch(branch)

        env = os.environ.copy()
        env["MK8S_SERIES"] = self.series
        env["MK8S_CHARM"] = "ch:microk8s"
        env["MK8S_CHARM_CHANNEL"] = channel

        # Passing '-c' will force pytest not to use the pytest.ini from the jenkins repo
        cmd = f"tox -e integration-3.1 -- --maxfail=1 --controller '{controller}' -c /dev/null"
        self._run_cmd(cmd, _cwd=Path("charm-microk8s"), _env=env)
        return True

    def do_release(self, from_channel, to_channel):
        req = ReleaseRequestModel(
            channel=to_channel, revision=self.get_channel_revision(from_channel)
        )
        store_client = CharmhubHelper.get_store_client()
        store_client.release(name="microk8s", release_request=[req])


class Configuration:
    def __init__(self):
        self.series = os.environ.get("SERIES", "jammy")
        self.arch = os.environ.get("ARCH", "amd64")
        self.from_channel = os.environ.get("FROM_CHANNEL", "latest/edge")
        self.to_channel = os.environ.get("TO_CHANNEL", "latest/beta")
        skip_tests_env = os.environ.get("SKIP_TESTS", "false")
        self.skip_tests = skip_tests_env == "true"
        self.juju_controller = os.environ.get("CONTROLLER")
        if self.juju_controller and self.juju_controller.strip() == "":
            self.juju_controller = None
        dry_run_env = os.environ.get("DRY_RUN", "false")
        self.dry_run = dry_run_env != "false"
        self.tests_repo = os.environ.get(
            "REPOSITORY", "https://github.com/canonical/charm-microk8s"
        )
        if self.tests_repo and self.tests_repo.strip() == "":
            self.tests_repo = "https://github.com/canonical/charm-microk8s"
        self.tests_branch = os.environ.get("BRANCH")
        if not self.tests_branch or self.tests_branch.strip() == "":
            if self.from_channel.startswith("1."):
                self.version = self.from_channel.split("/")[0]
                self.tests_branch = f"release-{self.version}"
            else:
                self.tests_branch = f"master"  # wokeignore:rule=master

    def print(self):
        """
        Print requested setup on the release job
        """
        click.echo(f"Release from: {self.from_channel} (FROM_CHANNEL)")
        click.echo(f"Release to: {self.to_channel} (TO_CHANNEL)")
        click.echo(f"Architecture: {self.arch} (ARCH)")
        click.echo(f"Skip tests: {self.skip_tests} (SKIP_TESTS)")
        click.echo(f"Tests taken from repo: {self.tests_repo} (REPOSITORY)")
        click.echo(f"Tests taken from branch: {self.tests_branch} (BRANCH)")
        click.echo(f"Tests run on: {self.series} (SERIES)")
        click.echo(f"Juju controller to use: {self.juju_controller} (CONTROLLER)")
        click.echo(f"This is a dry run: {self.dry_run} (DRY_RUN)")

    def valid(self) -> bool:
        """
        Do some basic checks on the environment variables passed
        """
        if "CHARMCRAFT_AUTH" not in os.environ:
            click.echo(
                "CHARMCRAFT_AUTH is not set. Export charmstore credentials with:"
            )
            click.echo("  unset CHARMCRAFT_AUTH")
            click.echo("  charmcraft login --ttl 8766 --export ch.cred")
            click.echo("  export CHARMCRAFT_AUTH=$(cat ch.cred)")
            return False

        if not self.skip_tests and not self.juju_controller:
            click.echo("CONTROLLER is not set. Please, set the controller to test on.")
            return False

        return True
