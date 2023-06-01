#
# Copyright 2023 Canonical, Ltd.
#

import ops
import ops.testing
import pytest
from conftest import Environment
from ops.model import BlockedStatus, WaitingStatus


@pytest.mark.parametrize("role", ["worker", "control-plane", ""])
def test_install_channel(role, e: Environment):
    e.harness.update_config({"role": role, "channel": "fakechannel"})
    e.harness.begin_with_initial_hooks()

    e.util.install_required_packages.assert_called_once()
    e.microk8s.install.assert_called_once_with("fakechannel")


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
    e.harness.charm._on_remove(None)

    e.microk8s.uninstall.assert_called_once()


def test_update_status(e: Environment):
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus2")
    e.harness.begin_with_initial_hooks()

    e.microk8s.get_unit_status.assert_not_called()

    e.harness.charm._on_update_status(None)
    e.microk8s.get_unit_status.assert_not_called()

    e.harness.charm._state.joined = True
    e.harness.charm._on_update_status(None)
    e.microk8s.get_unit_status.assert_called_once_with(e.gethostname.return_value)
    assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus2")
