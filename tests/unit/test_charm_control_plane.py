#
# Copyright 2023 Canonical, Ltd.
#
import subprocess
from unittest import mock

import ops
import ops.testing
import pytest
from conftest import Environment


@pytest.mark.parametrize("is_leader", [True, False])
def test_install(e: Environment, is_leader: bool):
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(is_leader)
    e.harness.begin_with_initial_hooks()

    e.util.install_required_packages.assert_called_once_with()
    e.microk8s.install.assert_called_once_with()
    e.microk8s.wait_ready.assert_called()
    e.microk8s.disable_cert_reissue.assert_not_called()

    if not is_leader:
        assert isinstance(e.harness.charm.unit.status, ops.model.WaitingStatus)
        e.microk8s.configure_hostpath_storage.assert_not_called()
        e.microk8s.write_local_kubeconfig.assert_not_called()
    else:
        e.microk8s.configure_hostpath_storage.assert_called_once_with(False)
        e.microk8s.write_local_kubeconfig.assert_called()
        assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus")
        assert e.harness.charm._state.joined

    assert e.harness.charm.model.unit.opened_ports() == {
        ops.model.OpenedPort(protocol="tcp", port=16443),
    }


def test_leader_peer_relation(e: Environment):
    e.microk8s.add_node.return_value = "01010101010101010101010101010101"

    e.harness.add_network("10.10.10.10")
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()

    rel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.add_relation_unit(rel_id, f"{e.harness.charm.app.name}/1")
    e.harness.update_relation_data(rel_id, f"{e.harness.charm.app.name}/1", {"hostname": "f-1"})

    e.microk8s.add_node.assert_called_once_with()
    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    assert relation_data["join_token"] == "01010101010101010101010101010101"
    assert relation_data["join_url"] == "10.10.10.10:25000/01010101010101010101010101010101"
    assert e.harness.charm._state.hostnames[f"{e.harness.charm.app.name}/1"] == "f-1"

    e.harness.remove_relation_unit(rel_id, f"{e.harness.charm.app.name}/1")
    e.microk8s.remove_node.assert_called_once_with("f-1")


def test_leader_peer_relation_leave(e: Environment):
    fakeaddress = "10.10.10.10"
    e.microk8s.add_node.return_value = "faketoken"

    e.harness.add_network(fakeaddress)
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()

    rel = e.harness.charm.model.get_relation("peer")
    e.harness.add_relation_unit(rel.id, f"{e.harness.charm.app.name}/1")
    e.harness.update_relation_data(rel.id, f"{e.harness.charm.app.name}/1", {"hostname": "f-1"})
    e.microk8s.get_unit_status.return_value = ops.model.WaitingStatus("waiting for node")

    # NOTE(neoaggelos): mock self departed event
    e.harness.charm.on.peer_relation_departed.emit(
        relation=rel,
        app=e.harness.charm.app,
        unit=e.harness.charm.unit,
        departing_unit_name=e.harness.charm.unit.name,
    )

    relation_data = e.harness.get_relation_data(rel.id, e.harness.charm.app.name)
    assert relation_data["remove_nodes"] == '["fakehostname"]'


def test_leader_control_plane_relation(e: Environment):
    e.microk8s.add_node.return_value = "01010101010101010101010101010101"

    e.harness.add_network("10.10.10.10")
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()

    rel_id = e.harness.add_relation("workers", "microk8s-worker")
    e.harness.add_relation_unit(rel_id, "microk8s-worker/0")
    e.harness.update_relation_data(rel_id, "microk8s-worker/0", {"hostname": "f-1"})

    e.microk8s.add_node.assert_called_once_with()
    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    assert relation_data["join_token"] == "01010101010101010101010101010101"
    assert relation_data["join_url"] == "10.10.10.10:25000/01010101010101010101010101010101"
    assert e.harness.charm._state.hostnames["microk8s-worker/0"] == "f-1"

    e.harness.remove_relation_unit(rel_id, "microk8s-worker/0")
    e.microk8s.remove_node.assert_called_once_with("f-1")
    assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus")


def test_follower_peer_relation(e: Environment):
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


def test_follower_control_plane_relation(e: Environment):
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()
    e.harness.set_leader(False)

    rel_id = e.harness.add_relation("workers", "microk8s-worker")
    e.harness.add_relation_unit(rel_id, "microk8s-worker/0")
    e.harness.update_relation_data(rel_id, "microk8s-worker/0", {"hostname": "f-1"})

    relation_data = e.harness.get_relation_data(rel_id, e.harness.charm.app)
    assert "join_url" not in relation_data
    e.microk8s.add_node.assert_not_called()
    assert e.harness.charm._state.hostnames["microk8s-worker/0"] == "f-1"

    e.harness.remove_relation_unit(rel_id, "microk8s-worker/0")
    e.microk8s.remove_node.assert_not_called()


def test_follower_retrieve_join_url(e: Environment):
    e.harness.update_config({"role": "control-plane", "automatic_certificate_reissue": False})
    e.harness.set_leader(False)
    e.harness.begin_with_initial_hooks()

    e.microk8s.write_local_kubeconfig.assert_not_called()
    e.microk8s.disable_cert_reissue.assert_not_called()
    e.microk8s.configure_extra_sans.assert_not_called()
    assert not e.harness.charm._state.joined

    rel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.add_relation_unit(rel_id, f"{e.harness.charm.app.name}/1")
    e.harness.update_relation_data(rel_id, e.harness.charm.app.name, {"join_url": "fakejoinurl"})

    e.microk8s.join.assert_called_once_with("fakejoinurl", False)
    e.microk8s.wait_ready.assert_called_with()
    e.microk8s.get_unit_status.assert_called_with("fakehostname")
    e.microk8s.write_local_kubeconfig.assert_called()
    e.microk8s.configure_extra_sans.assert_called_once_with("%UNIT_PUBLIC_ADDRESS%")
    assert (
        e.harness.get_relation_data(rel_id, e.harness.charm.unit.name)["configured_ca_crt"]
        == "fakeca"
    )

    assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus")
    assert e.harness.charm._state.joined


@pytest.mark.parametrize("become_leader", [True, False])
def test_follower_become_leader_remove_departing_nodes(e: Environment, become_leader: bool):
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(False)
    e.harness.begin_with_initial_hooks()

    prel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.add_relation_unit(prel_id, f"{e.harness.charm.app.name}/1")
    e.harness.add_relation_unit(prel_id, f"{e.harness.charm.app.name}/2")
    e.harness.update_relation_data(prel_id, f"{e.harness.charm.app.name}/1", {"hostname": "f-2"})
    e.harness.update_relation_data(prel_id, e.harness.charm.app.name, {"join_url": "fakejoinurl"})

    rel_id = e.harness.add_relation("workers", "microk8s-worker")
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

    assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus")


@pytest.mark.parametrize("become_leader", [True, False])
def test_follower_become_leader_remove_already_departed_nodes(e: Environment, become_leader: bool):
    e.harness.update_config({"role": "control-plane"})
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

    assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus")


@pytest.mark.parametrize("become_leader", [True, False])
def test_follower_become_leader_keep_join_token(e: Environment, become_leader: bool):
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(False)
    e.harness.add_network("10.10.10.10")
    e.harness.begin_with_initial_hooks()

    prel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.update_relation_data(
        prel_id,
        e.harness.charm.app.name,
        {"join_token": "faketoken", "join_url": "11.11.11.11:25000/faketoken"},
    )
    e.harness.set_leader(become_leader)

    e.harness.add_relation_unit(prel_id, f"{e.harness.charm.app.name}/1")
    e.harness.add_relation_unit(prel_id, f"{e.harness.charm.app.name}/2")

    e.microk8s.add_node.assert_not_called()
    data = e.harness.get_relation_data(prel_id, e.harness.charm.app.name)
    assert data["join_token"] == "faketoken"
    if become_leader:
        assert data["join_url"] == "10.10.10.10:25000/faketoken"
    else:
        assert data["join_url"] == "11.11.11.11:25000/faketoken"

    assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus")


@pytest.mark.parametrize("role", ["", "control-plane"])
@pytest.mark.parametrize("is_leader", [False, True])
@pytest.mark.parametrize("has_joined", [False, True])
def test_build_scrape_configs(e: Environment, role: str, is_leader: bool, has_joined: bool):
    e.metrics.get_tls_auth.return_value = ("fakecrt", "fakekey")

    e.harness.update_config({"role": role})
    e.harness.set_leader(is_leader)
    e.harness.begin_with_initial_hooks()

    e.harness.charm._state.joined = has_joined

    # no token yet, assert empty jobs
    result = e.harness.charm._build_scrape_configs()
    assert not result
    e.metrics.build_scrape_jobs.assert_not_called()

    # metrics token from relation
    rel_id = e.harness.model.get_relation("peer").id
    e.harness.update_relation_data(
        rel_id, e.harness.charm.app.name, {"metrics_crt": "fakecrt", "metrics_key": "fakekey"}
    )

    # we now have a token, regenerate jobs
    result = e.harness.charm._build_scrape_configs()
    if not has_joined:
        assert not result
        e.metrics.build_scrape_jobs.assert_not_called()
    else:
        e.metrics.build_scrape_jobs.assert_called_once_with(
            "fakecrt", "fakekey", True, "fakehostname"
        )
        assert result == e.metrics.build_scrape_jobs.return_value


@pytest.mark.parametrize("is_leader", (True, False))
def test_cos_agent_relation(e: Environment, is_leader: bool):
    e.microk8s.add_node.return_value = "faketoken"
    e.metrics.build_scrape_jobs.return_value = [{"job_name": "fakejob"}]
    e.metrics.get_tls_auth.return_value = ("fakecrt", "fakekey")

    e.harness.add_network("10.10.10.10")
    e.harness.update_config({"role": "control-plane"})
    e.harness.set_leader(True)
    e.harness.begin_with_initial_hooks()

    e.harness.set_leader(is_leader)

    e.metrics.apply_required_resources.assert_not_called()
    e.metrics.get_tls_auth.assert_not_called()
    e.metrics.build_scrape_jobs.assert_not_called()

    worker_rel_id = e.harness.add_relation("workers", "microk8s-worker")
    e.harness.add_relation_unit(worker_rel_id, "microk8s-worker/0")

    metrics_rel_id = e.harness.add_relation("cos-agent", "grafana-agent")
    e.harness.add_relation_unit(metrics_rel_id, "grafana-agent/0")
    peer_rel_id = e.harness.model.get_relation("peer").id
    peer_data = e.harness.get_relation_data(peer_rel_id, e.harness.charm.app.name)
    metrics_data = e.harness.get_relation_data(metrics_rel_id, e.harness.charm.app.name)
    workers_data = e.harness.get_relation_data(worker_rel_id, e.harness.charm.app.name)

    e.COSAgentProvider.assert_called_once_with(
        e.harness.charm,
        relation_name="cos-agent",
        scrape_configs=e.harness.charm._build_scrape_configs,
        metrics_rules_dir="src/prometheus_alert_rules",
        dashboard_dirs=["src/grafana_dashboards"],
        refresh_events=mock.ANY,
    )
    # assert refresh_events using their names
    called_with_refresh_events = e.COSAgentProvider.mock_calls[0].kwargs["refresh_events"]
    assert {evt.event_kind for evt in called_with_refresh_events} == {
        "peer_relation_changed",
        "upgrade_charm",
    }

    if is_leader:
        e.metrics.apply_required_resources.assert_called_once_with()
        e.metrics.get_tls_auth.assert_called_once_with()

        for data in (peer_data, workers_data):
            assert data["metrics_crt"] == "fakecrt"
            assert data["metrics_key"] == "fakekey"
    else:
        e.metrics.apply_required_resources.assert_not_called()
        e.metrics.get_tls_auth.assert_not_called()

        assert metrics_data == {}
        assert workers_data == {}
        assert "metrics_crt" not in peer_data
        assert "metrics_key" not in peer_data

    e.metrics.apply_required_resources.reset_mock()
    e.metrics.get_tls_auth.reset_mock()
    e.metrics.build_scrape_jobs.reset_mock()

    e.metrics.get_tls_auth.return_value = ("fakecrt2", "fakekey2")

    # assert metrics token is updated on update_status
    e.harness.charm.on.update_status.emit()
    e.metrics.apply_required_resources.assert_not_called()
    if is_leader:
        e.metrics.get_tls_auth.assert_called_once_with()
        for data in (peer_data, workers_data):
            assert data["metrics_crt"] == "fakecrt2"
            assert data["metrics_key"] == "fakekey2"
    else:
        e.metrics.get_tls_auth.assert_not_called()

    e.metrics.get_tls_auth.reset_mock()
    e.metrics.get_tls_auth.return_value = ("fakecrt3", "fakekey3")
    e.metrics.get_tls_auth.side_effect = subprocess.CalledProcessError(1, "fakeerror")

    # assert metrics token is updated on update_status
    e.harness.charm.on.update_status.emit()
    e.metrics.apply_required_resources.assert_not_called()
    if is_leader:
        e.metrics.get_tls_auth.assert_called_once_with()
        for data in (peer_data, workers_data):
            assert data["metrics_crt"] == "fakecrt2"
            assert data["metrics_key"] == "fakekey2"
    else:
        e.metrics.get_tls_auth.assert_not_called()
