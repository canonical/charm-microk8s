#
# Copyright 2023 Canonical, Ltd.
#
from unittest import mock

import ops
import ops.testing
from conftest import Environment


def test_install(e: Environment):
    e.uname.return_value.release = "fakerelease"

    e.harness.update_config({"role": "control-plane"})
    e.harness.begin_with_initial_hooks()

    e.uname.assert_called_once()
    e.check_call.assert_has_calls(
        [
            mock.call(["apt-get", "install", "--yes", "nfs-common"]),
            mock.call(["apt-get", "install", "--yes", "open-iscsi"]),
            mock.call(["apt-get", "install", "--yes", "linux-modules-extra-fakerelease"]),
            mock.call(["snap", "install", "microk8s", "--classic"]),
        ]
    )

    assert e.harness.charm.model.unit.opened_ports() == {
        ops.model.OpenedPort(protocol="tcp", port=80),
        ops.model.OpenedPort(protocol="tcp", port=443),
        ops.model.OpenedPort(protocol="tcp", port=16443),
    }


def test_install_follower(e: Environment):
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(False)

    e.harness.begin_with_initial_hooks()
    assert isinstance(e.harness.charm.unit.status, ops.model.WaitingStatus)


def test_install_leader(e: Environment):
    e.node_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)

    e.harness.begin_with_initial_hooks()
    assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus")
    assert e.harness.charm._state.joined


def test_leader_add_unit_peer(e: Environment):
    faketoken = b"\x01" * 16
    fakeaddress = "10.10.10.10"
    e.node_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.get_hostname.return_value = "fakehostname"
    e.urandom.return_value = faketoken

    e.harness.add_network(fakeaddress)
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()

    e.check_call.reset_mock()

    rel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.add_relation_unit(rel_id, f"{e.harness.charm.app.name}/1")

    e.check_call.assert_called_with(
        ["microk8s", "add-node", "--token", faketoken.hex(), "--token-ttl", "7200"]
    )
    e.urandom.assert_called_once_with(16)
    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    assert relation_data["join_url"] == f"{fakeaddress}:25000/{faketoken.hex()}"


def test_leader_add_unit_worker(e: Environment):
    faketoken = b"\x01" * 16
    fakeaddress = "10.10.10.10"
    e.node_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.get_hostname.return_value = "fakehostname"
    e.urandom.return_value = faketoken

    e.harness.add_network(fakeaddress)
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()

    e.check_call.reset_mock()

    rel_id = e.harness.add_relation("microk8s-provides", "microk8s-worker")
    e.harness.add_relation_unit(rel_id, "microk8s-worker/0")

    e.check_call.assert_called_with(
        ["microk8s", "add-node", "--token", faketoken.hex(), "--token-ttl", "7200"]
    )
    e.urandom.assert_called_once_with(16)
    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    assert relation_data["join_url"] == f"{fakeaddress}:25000/{faketoken.hex()}"


def test_follower_add_unit_peer(e: Environment):
    e.node_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.get_hostname.return_value = "fakehostname"

    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()
    e.harness.set_leader(False)

    e.check_call.reset_mock()
    rel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.add_relation_unit(rel_id, f"{e.harness.charm.app.name}/1")

    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    assert "join_url" not in relation_data
    e.check_call.assert_not_called()
    e.urandom.assert_not_called()


def test_follower_add_unit_worker(e: Environment):
    e.node_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.get_hostname.return_value = "fakehostname"
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()
    e.harness.set_leader(False)

    e.check_call.reset_mock()

    rel_id = e.harness.add_relation("microk8s", "microk8s-worker")
    e.harness.add_relation_unit(rel_id, "microk8s-worker/0")

    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    assert "join_url" not in relation_data
    e.check_call.assert_not_called()
    e.urandom.assert_not_called()


def test_follower_retrieve_join_url(e: Environment):
    e.node_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.get_hostname.return_value = "fakehostname"

    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(False)
    e.harness.begin_with_initial_hooks()

    e.check_call.reset_mock()
    rel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.add_relation_unit(rel_id, f"{e.harness.charm.app.name}/1")
    e.harness.update_relation_data(rel_id, e.harness.charm.app.name, {"join_url": "fakejoinurl"})

    e.check_call.assert_called_with(["microk8s", "join", "fakejoinurl", "--worker"])
    e.node_status.assert_called_once_with("fakehostname")
