#
# Copyright 2023 Canonical, Ltd.
#

from unittest import mock

import ops
import ops.testing
import pytest
from conftest import Environment
from ops.model import BlockedStatus, WaitingStatus


@pytest.mark.parametrize("role", ["worker", "control-plane", ""])
@pytest.mark.parametrize(
    "channel, command",
    [
        ("", ["snap", "install", "microk8s", "--classic"]),
        ("1.27/stable", ["snap", "install", "microk8s", "--classic", "--channel", "1.27/stable"]),
        ("1.27-strict", ["snap", "install", "microk8s", "--classic", "--channel", "1.27-strict"]),
    ],
)
def test_install_channel(role, channel, command, e: Environment):
    e.harness.update_config({"role": role, "channel": channel})
    e.harness.begin_with_initial_hooks()

    e.check_call.assert_any_call(command)


@pytest.mark.parametrize(
    "role, expect_status",
    [
        ("", WaitingStatus),
        ("worker", WaitingStatus),
        ("control-plane", WaitingStatus),
        ("something else", BlockedStatus),
    ],
)
def test_verify_charm_role(e: Environment, role, expect_status):
    e.harness.update_config({"role": role})
    e.harness.begin_with_initial_hooks()

    assert isinstance(e.harness.charm.unit.status, expect_status)


def test_block_on_role_change(e: Environment):
    e.harness.update_config({"role": "worker"})
    e.harness.begin_with_initial_hooks()

    assert isinstance(e.harness.charm.model.unit.status, ops.model.WaitingStatus)

    e.harness.update_config({"role": "something else"})
    assert isinstance(e.harness.charm.model.unit.status, ops.model.BlockedStatus)

    e.harness.update_config({"role": "worker"})
    assert isinstance(e.harness.charm.model.unit.status, ops.model.WaitingStatus)


def test_remove(e: Environment):
    e.harness.begin_with_initial_hooks()
    e.check_call.reset_mock()
    e.harness.charm._on_remove(None)

    e.check_call.assert_called_once_with(["snap", "remove", "microk8s", "--purge"])


def test_update_status(e: Environment):
    e.node_to_unit_status.return_value = ops.model.ActiveStatus("fakestatus2")
    e.harness.begin_with_initial_hooks()

    e.node_to_unit_status.assert_not_called()

    e.harness.charm._on_update_status(None)
    e.node_to_unit_status.assert_not_called()

    e.harness.charm._state.joined = True
    e.harness.charm._on_update_status(None)
    e.node_to_unit_status.assert_called_once_with(e.get_hostname.return_value)
    assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus2")


@pytest.mark.parametrize("role", ["", "control-plane", "worker"])
@pytest.mark.parametrize("is_leader", [True, False])
def test_addons(e: Environment, role: str, is_leader: bool):
    e.node_to_unit_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.get_hostname.return_value = "fakehostname"

    e.harness.update_config({"role": role, "addons": ""})
    e.harness.set_leader(is_leader)
    e.harness.begin_with_initial_hooks()

    e.check_call.reset_mock()

    e.harness.update_config({"addons": "dns rbac"})
    e.harness.update_config({"addons": "dns"})
    e.harness.update_config({"addons": "dns ingress rbac"})
    e.harness.update_config({"addons": "dns:10.0.0.10 hostpath-storage ingress rbac"})
    e.harness.update_config({"addons": "dns:10.0.0.20 hostpath-storage ingress rbac"})

    if role in ["", "control-plane"] and is_leader:
        assert e.check_call.mock_calls == [
            # 1. enable dns and rbac
            mock.call(["microk8s", "enable", "dns"]),
            mock.call(["microk8s", "enable", "rbac"]),
            # 2. disable rbac
            mock.call(["microk8s", "disable", "rbac"]),
            # 3. enable ingress and rbac
            mock.call(["microk8s", "enable", "ingress"]),
            mock.call(["microk8s", "enable", "rbac"]),
            # 4. disable dns and re-enable with arguments, then enable hostpath-storage
            mock.call(["microk8s", "disable", "dns"]),
            mock.call(["microk8s", "enable", "dns:10.0.0.10"]),
            mock.call(["microk8s", "enable", "hostpath-storage"]),
            # 5. disable dns and re-enable with different arguments
            mock.call(["microk8s", "disable", "dns"]),
            mock.call(["microk8s", "enable", "dns:10.0.0.20"]),
        ]
    else:
        e.check_call.assert_not_called()
