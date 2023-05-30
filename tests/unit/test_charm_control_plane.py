#
# Copyright 2023 Canonical, Ltd.
#
from unittest import mock

import ops
import ops.testing
import pytest
from conftest import Environment


@pytest.mark.parametrize("is_leader", [True, False])
def test_install(e: Environment, is_leader: bool):
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")

    e.harness.update_config({"role": "control-plane", "addons": "dns"})
    e.harness.set_leader(is_leader)
    e.harness.begin_with_initial_hooks()

    e.util.install_required_packages.assert_called_once()
    e.microk8s.install.assert_called_once_with("")
    e.microk8s.wait_ready.assert_called_once()

    if not is_leader:
        e.microk8s.reconcile_addons.assert_not_called()
        assert isinstance(e.harness.charm.unit.status, ops.model.WaitingStatus)
    else:
        e.microk8s.reconcile_addons.assert_called_once_with([], ["dns"])
        assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus")
        assert e.harness.charm._state.joined

    assert e.harness.charm.model.unit.opened_ports() == {
        ops.model.OpenedPort(protocol="tcp", port=80),
        ops.model.OpenedPort(protocol="tcp", port=443),
        ops.model.OpenedPort(protocol="tcp", port=16443),
    }


def test_leader_peer_relation(e: Environment):
    e.microk8s.add_node.return_value = "01010101010101010101010101010101"
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.gethostname.return_value = "fakehostname"

    e.harness.add_network("10.10.10.10")
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()

    rel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.add_relation_unit(rel_id, f"{e.harness.charm.app.name}/1")
    e.harness.update_relation_data(rel_id, f"{e.harness.charm.app.name}/1", {"hostname": "f-1"})

    e.microk8s.add_node.assert_called_once()
    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    assert relation_data["join_url"] == "10.10.10.10:25000/01010101010101010101010101010101"
    assert e.harness.charm._state.hostnames[f"{e.harness.charm.app.name}/1"] == "f-1"

    e.harness.remove_relation_unit(rel_id, f"{e.harness.charm.app.name}/1")
    e.microk8s.remove_node.assert_called_once_with("f-1")


def test_leader_peer_relation_leave(e: Environment):
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.gethostname.return_value = "fakehostname"
    fakeaddress = "10.10.10.10"

    e.harness.add_network(fakeaddress)
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()

    rel = e.harness.charm.model.get_relation("peer")
    e.harness.add_relation_unit(rel.id, f"{e.harness.charm.app.name}/1")
    e.harness.update_relation_data(rel.id, f"{e.harness.charm.app.name}/1", {"hostname": "f-1"})

    # NOTE(neoaggelos): mock self departed event
    e.harness.charm.on["peer"].relation_departed.emit(
        relation=rel,
        app=e.harness.charm.app,
        unit=e.harness.charm.unit,
        departing_unit_name=e.harness.charm.unit.name,
    )

    relation_data = e.harness.get_relation_data(rel.id, e.harness.charm.app.name)
    assert relation_data["remove_nodes"] == '["fakehostname"]'


def test_leader_microk8s_provides_relation(e: Environment):
    e.microk8s.add_node.return_value = "01010101010101010101010101010101"
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.gethostname.return_value = "fakehostname"

    e.harness.add_network("10.10.10.10")
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()

    rel_id = e.harness.add_relation("microk8s-provides", "microk8s-worker")
    e.harness.add_relation_unit(rel_id, "microk8s-worker/0")
    e.harness.update_relation_data(rel_id, "microk8s-worker/0", {"hostname": "f-1"})

    e.microk8s.add_node.assert_called_once()
    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    assert relation_data["join_url"] == "10.10.10.10:25000/01010101010101010101010101010101"
    assert e.harness.charm._state.hostnames["microk8s-worker/0"] == "f-1"

    e.harness.remove_relation_unit(rel_id, "microk8s-worker/0")
    e.microk8s.remove_node.assert_called_once_with("f-1")


def test_follower_peer_relation(e: Environment):
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.gethostname.return_value = "fakehostname"

    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()
    e.harness.set_leader(False)

    rel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.add_relation_unit(rel_id, f"{e.harness.charm.app.name}/1")
    e.harness.update_relation_data(rel_id, f"{e.harness.charm.app.name}/1", {"hostname": "f-1"})

    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    assert "join_url" not in relation_data
    e.microk8s.add_node.assert_not_called()
    assert e.harness.charm._state.hostnames[f"{e.harness.charm.app.name}/1"] == "f-1"

    e.harness.remove_relation_unit(rel_id, f"{e.harness.charm.app.name}/1")
    e.microk8s.remove_node.assert_not_called()


def test_follower_microk8s_provides_relation(e: Environment):
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.gethostname.return_value = "fakehostname"
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()
    e.harness.set_leader(False)

    rel_id = e.harness.add_relation("microk8s-provides", "microk8s-worker")
    e.harness.add_relation_unit(rel_id, "microk8s-worker/0")
    e.harness.update_relation_data(rel_id, "microk8s-worker/0", {"hostname": "f-1"})

    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    assert "join_url" not in relation_data
    e.microk8s.add_node.assert_not_called()
    assert e.harness.charm._state.hostnames["microk8s-worker/0"] == "f-1"

    e.harness.remove_relation_unit(rel_id, "microk8s-worker/0")
    e.microk8s.remove_node.assert_not_called()


def test_follower_retrieve_join_url(e: Environment):
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.gethostname.return_value = "fakehostname"

    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(False)
    e.harness.begin_with_initial_hooks()

    assert not e.harness.charm._state.joined

    rel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.add_relation_unit(rel_id, f"{e.harness.charm.app.name}/1")
    e.harness.update_relation_data(rel_id, e.harness.charm.app.name, {"join_url": "fakejoinurl"})

    e.microk8s.join.assert_called_once_with("fakejoinurl", False)
    e.microk8s.get_unit_status.assert_called_once_with("fakehostname")

    assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus")
    assert e.harness.charm._state.joined


@pytest.mark.parametrize("become_leader", [True, False])
def test_follower_become_leader_remove_departing_nodes(e: Environment, become_leader: bool):
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.gethostname.return_value = "fakehostname"

    e.harness.update_config({"role": "control-plane", "addons": ""})
    e.harness.set_leader(False)
    e.harness.begin_with_initial_hooks()

    prel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.add_relation_unit(prel_id, f"{e.harness.charm.app.name}/1")
    e.harness.add_relation_unit(prel_id, f"{e.harness.charm.app.name}/2")
    e.harness.update_relation_data(prel_id, f"{e.harness.charm.app.name}/1", {"hostname": "f-2"})
    e.harness.update_relation_data(prel_id, e.harness.charm.app.name, {"join_url": "fakejoinurl"})

    rel_id = e.harness.add_relation("microk8s-provides", "microk8s-worker")
    e.harness.add_relation_unit(rel_id, "microk8s-worker/0")
    e.harness.add_relation_unit(rel_id, "microk8s-worker/1")
    e.harness.update_relation_data(rel_id, "microk8s-worker/0", {"hostname": "f-1"})

    if become_leader:
        e.harness.set_leader(become_leader)

    e.harness.remove_relation_unit(rel_id, "microk8s-worker/0")
    e.harness.remove_relation_unit(rel_id, "microk8s-worker/1")
    e.harness.remove_relation_unit(prel_id, f"{e.harness.charm.app.name}/1")
    e.harness.remove_relation_unit(prel_id, f"{e.harness.charm.app.name}/2")

    if become_leader:
        assert sorted(e.microk8s.remove_node.mock_calls) == [mock.call("f-1"), mock.call("f-2")]
    else:
        e.microk8s.remove_node.assert_not_called()


@pytest.mark.parametrize("become_leader", [True, False])
def test_follower_become_leader_remove_already_departed_nodes(e: Environment, become_leader: bool):
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")
    e.gethostname.return_value = "fakehostname"

    e.harness.update_config({"role": "control-plane", "addons": ""})
    e.harness.set_leader(False)
    e.harness.begin_with_initial_hooks()

    prel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.add_relation_unit(prel_id, f"{e.harness.charm.app.name}/1")
    e.harness.add_relation_unit(prel_id, f"{e.harness.charm.app.name}/2")
    e.harness.update_relation_data(prel_id, f"{e.harness.charm.app.name}/1", {"hostname": "f-2"})

    e.harness.update_relation_data(prel_id, e.harness.charm.app.name, {"join_url": "fakejoinurl"})

    e.harness.update_relation_data(
        prel_id, e.harness.charm.app.name, {"remove_nodes": '["f-1", "f-2", "fakehostname"]'}
    )

    e.harness.set_leader(become_leader)
    if become_leader:
        assert sorted(e.microk8s.remove_node.mock_calls) == [mock.call("f-1"), mock.call("f-2")]
    else:
        e.microk8s.remove_node.assert_not_called()
