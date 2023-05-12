# Copyright 2023 Angelos Kolaitis
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

from unittest import mock

import ops
import ops.testing
import pytest
from ops.model import BlockedStatus, WaitingStatus

from charm import MicroK8sCharm


@pytest.fixture
def harness():
    harness = ops.testing.Harness(MicroK8sCharm)
    yield harness
    harness.cleanup()


@mock.patch("subprocess.check_call")
@pytest.mark.parametrize("role", ["worker", "control-plane", ""])
@pytest.mark.parametrize(
    "channel, command",
    [
        ("", ["snap", "install", "microk8s", "--classic"]),
        ("1.27/stable", ["snap", "install", "microk8s", "--classic", "--channel", "1.27/stable"]),
        ("1.27-strict", ["snap", "install", "microk8s", "--classic", "--channel", "1.27-strict"]),
    ],
)
def test_install_channel(_check_call, role, channel, command, harness: ops.testing.Harness):
    harness.update_config({"role": role, "channel": channel})
    harness.begin_with_initial_hooks()

    _check_call.assert_any_call(command)


@mock.patch("subprocess.check_call")
@pytest.mark.parametrize(
    "role, expect_status",
    [
        ("", WaitingStatus),
        ("worker", WaitingStatus),
        ("control-plane", WaitingStatus),
        ("something else", BlockedStatus),
    ],
)
def test_verify_charm_role(_check_call, role, expect_status, harness: ops.testing.Harness):
    harness.update_config({"role": role})
    harness.begin_with_initial_hooks()

    assert isinstance(harness.charm.unit.status, expect_status)


@mock.patch("subprocess.check_call")
def test_block_on_role_change(_check_call, harness: ops.testing.Harness):
    harness.update_config({"role": "worker"})
    harness.begin_with_initial_hooks()

    assert isinstance(harness.charm.model.unit.status, ops.model.WaitingStatus)

    harness.update_config({"role": "something else"})
    assert isinstance(harness.charm.model.unit.status, ops.model.BlockedStatus)

    harness.update_config({"role": "worker"})
    assert isinstance(harness.charm.model.unit.status, ops.model.WaitingStatus)


@mock.patch("subprocess.check_call")
@mock.patch("subprocess.run")
def test_remove(_run, _check_call, harness: ops.testing.Harness):
    harness.begin_with_initial_hooks()
    harness.charm._on_remove(None)

    _run.assert_called_once_with(["snap", "remove", "microk8s", "--purge"])
