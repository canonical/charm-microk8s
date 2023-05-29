#
# Copyright 2023 Canonical, Ltd.
#
from unittest import mock

import ops
import ops.testing
import pytest
from conftest import Environment


def test_install(e: Environment):
    e.uname.return_value.release = "fakerelease"

    e.harness.update_config({"role": "worker"})
    e.harness.begin_with_initial_hooks()

    e.uname.assert_called_once()
    assert e.check_call.mock_calls == [
        mock.call(["apt-get", "install", "--yes", "nfs-common"]),
        mock.call(["apt-get", "install", "--yes", "open-iscsi"]),
        mock.call(["apt-get", "install", "--yes", "linux-modules-extra-fakerelease"]),
        mock.call(["snap", "install", "microk8s", "--classic"]),
        mock.call(["microk8s", "status", "--wait-ready", "--timeout=30"]),
    ]

    assert e.harness.charm.model.unit.opened_ports() == {
        ops.model.OpenedPort(protocol="tcp", port=80),
        ops.model.OpenedPort(protocol="tcp", port=443),
    }

    assert isinstance(e.harness.charm.model.unit.status, ops.model.WaitingStatus)


@pytest.mark.parametrize("is_leader", [True, False])
def test_microk8s_provides_relation(e: Environment, is_leader: bool):
    e.node_to_unit_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.get_hostname.return_value = "fakehostname"

    e.harness.update_config({"role": "worker"})
    e.harness.set_leader(is_leader)
    e.harness.begin_with_initial_hooks()
    unit = e.harness.charm.model.unit
    assert isinstance(unit.status, ops.model.WaitingStatus)

    e.check_call.reset_mock()

    rel_id = e.harness.add_relation("microk8s", "microk8s-cp")
    e.harness.add_relation_unit(rel_id, "microk8s-cp/0")
    e.harness.update_relation_data(rel_id, "microk8s-cp", {"join_url": "fakejoinurl"})

    e.check_call.assert_called_once_with(["microk8s", "join", "fakejoinurl", "--worker"])
    e.node_to_unit_status.assert_called_once_with("fakehostname")
    assert unit.status == ops.model.ActiveStatus("fakestatus")
    assert e.harness.get_relation_data(rel_id, e.harness.charm.unit)["hostname"] == "fakehostname"

    e.check_call.reset_mock()

    e.harness.remove_relation(rel_id)

    e.check_call.assert_called_once_with(["snap", "remove", "microk8s", "--purge"])
    assert isinstance(unit.status, ops.model.WaitingStatus)


def test_microk8s_provides_invalid_relation(e: Environment):
    e.node_to_unit_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.get_hostname.return_value = "fakehostname"

    e.harness.update_config({"role": "worker"})
    e.harness.begin_with_initial_hooks()
    assert isinstance(e.harness.charm.model.unit.status, ops.model.WaitingStatus)

    e.check_call.reset_mock()

    rel_id = e.harness.add_relation("microk8s", "microk8s")
    e.harness.add_relation_unit(rel_id, "microk8s/0")
    e.harness.update_relation_data(rel_id, "microk8s", {"not_a_join_url": "fakejoinurl"})

    assert e.harness.get_relation_data(rel_id, e.harness.charm.unit)["hostname"] == "fakehostname"

    e.check_call.assert_not_called()
    assert isinstance(e.harness.charm.model.unit.status, ops.model.WaitingStatus)

    e.check_call.reset_mock()

    e.harness.remove_relation_unit(rel_id, "microk8s/0")
    e.harness.remove_relation(rel_id)

    e.check_call.assert_not_called()
    assert isinstance(e.harness.charm.model.unit.status, ops.model.WaitingStatus)


@pytest.mark.parametrize("is_leader", [True, False])
def test_microk8s_provides_relation_departed(e: Environment, is_leader: bool):
    e.node_to_unit_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.get_hostname.return_value = "fakehostname"

    e.harness.update_config({"role": "worker"})
    e.harness.set_leader(is_leader)
    e.harness.begin_with_initial_hooks()
    unit = e.harness.charm.model.unit
    assert isinstance(unit.status, ops.model.WaitingStatus)

    e.check_call.reset_mock()

    rel_id = e.harness.add_relation("microk8s", "microk8s-cp")
    e.harness.add_relation_unit(rel_id, "microk8s-cp/0")
    e.harness.add_relation_unit(rel_id, "microk8s-cp/1")
    e.harness.update_relation_data(rel_id, "microk8s-cp", {"join_url": "fakejoinurl"})

    e.check_call.assert_called_once_with(["microk8s", "join", "fakejoinurl", "--worker"])
    e.node_to_unit_status.assert_called_once_with("fakehostname")
    assert unit.status == ops.model.ActiveStatus("fakestatus")
    assert e.harness.get_relation_data(rel_id, e.harness.charm.unit)["hostname"] == "fakehostname"

    e.check_call.reset_mock()

    e.harness.remove_relation_unit(rel_id, "microk8s-cp/1")
    e.check_call.assert_not_called()

    assert unit.status == ops.model.ActiveStatus("fakestatus")
