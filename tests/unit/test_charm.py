#
# Copyright 2023 Canonical, Ltd.
#

import subprocess
from unittest import mock

import ops
import ops.testing
import pytest
from conftest import Environment
from ops.model import BlockedStatus, WaitingStatus


@pytest.mark.parametrize("role", ["worker", "control-plane", ""])
def test_install(role, e: Environment):
    e.harness.update_config(
        {
            "role": role,
            "containerd_http_proxy": "fakehttpproxy",
            "containerd_https_proxy": "fakehttpsproxy",
            "containerd_no_proxy": "fakenoproxy",
        }
    )
    e.harness.begin_with_initial_hooks()

    e.util.install_required_packages.assert_called_once_with()
    e.microk8s.install.assert_called_once_with()
    e.microk8s.set_containerd_proxy_options.assert_called_once_with(
        "fakehttpproxy", "fakehttpsproxy", "fakenoproxy"
    )


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

    # remove uninstalls
    e.harness.charm.on.remove.emit()
    e.microk8s.uninstall.assert_called_once_with()

    # exceptions in uninstall are ignored
    e.microk8s.uninstall.reset_mock()
    e.microk8s.uninstall.side_effect = subprocess.CalledProcessError(1, "fake exception")
    e.harness.charm.on.remove.emit()
    e.microk8s.uninstall.assert_called_once_with()


def test_update_status(e: Environment):
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus2")
    e.microk8s.get_kubernetes_version.return_value = None

    e.harness.begin_with_initial_hooks()

    e.microk8s.get_unit_status.assert_not_called()
    e.microk8s.get_kubernetes_version.assert_not_called()

    e.harness.charm.on.update_status.emit()
    e.microk8s.get_unit_status.assert_not_called()
    e.microk8s.get_kubernetes_version.assert_not_called()

    e.harness.charm._state.joined = True
    e.harness.charm.on.update_status.emit()
    e.microk8s.get_unit_status.assert_called_once_with(e.gethostname.return_value)
    e.microk8s.get_kubernetes_version.assert_called_once_with()
    assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus2")
    assert e.harness.charm.unit._backend._workload_version is None

    # reset
    e.microk8s.get_unit_status.reset_mock()
    e.microk8s.get_kubernetes_version.reset_mock()
    e.microk8s.get_kubernetes_version.return_value = "fakeversion"

    # test retry until active status
    e.microk8s.get_unit_status.side_effect = [
        ops.model.WaitingStatus("s"),
        ops.model.ActiveStatus("fakestatus3"),
    ]
    e.harness.charm.on.update_status.emit()

    assert e.microk8s.get_unit_status.mock_calls == [mock.call(e.gethostname.return_value)] * 2
    assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus3")
    assert e.harness.charm.unit._backend._workload_version == "fakeversion"


@pytest.mark.parametrize("role", ["", "control-plane"])
@pytest.mark.parametrize("has_joined", [False, True])
def test_config_disable_cert_reissue(e: Environment, role: str, has_joined: bool):
    e.harness.update_config({"role": role, "automatic_certificate_reissue": True})
    e.harness.set_leader(has_joined)
    e.harness.begin_with_initial_hooks()

    e.harness.charm._state.joined = has_joined

    e.harness.update_config({"automatic_certificate_reissue": True})
    e.harness.update_config({"automatic_certificate_reissue": False})

    if has_joined:
        e.microk8s.disable_cert_reissue.assert_called_once_with()
    else:
        e.microk8s.disable_cert_reissue.assert_not_called()


@pytest.mark.parametrize("role", ["", "control-plane"])
@pytest.mark.parametrize("has_joined", [False, True])
def test_config_extra_sans(e: Environment, role: str, has_joined: bool):
    e.harness.update_config({"role": role, "extra_sans": ""})
    e.harness.set_leader(has_joined)
    e.harness.begin_with_initial_hooks()

    e.harness.charm._state.joined = has_joined
    e.microk8s.configure_extra_sans.reset_mock()

    e.harness.update_config({"extra_sans": "2.2.2.2,k8s.local"})

    if has_joined:
        e.microk8s.configure_extra_sans.assert_called_once_with("2.2.2.2,k8s.local")
    else:
        e.microk8s.configure_extra_sans.assert_not_called()


@pytest.mark.parametrize("role", ["", "control-plane", "worker"])
def test_charm_upgrade(e: Environment, role: str):
    e.harness.update_config({"role": role, "automatic_certificate_reissue": True})
    e.harness.begin_with_initial_hooks()

    e.harness.charm.on.upgrade_charm.emit()

    e.microk8s.upgrade.assert_called_once_with()


@pytest.mark.parametrize("role", ["", "control-plane"])
@pytest.mark.parametrize("has_joined", [False, True])
def test_config_containerd_custom_registries(e: Environment, role: str, has_joined: bool):
    e.harness.update_config({"role": role, "containerd_custom_registries": "[]"})
    e.harness.set_leader(has_joined)
    e.harness.begin_with_initial_hooks()

    e.harness.charm._state.joined = has_joined

    e.containerd.parse_registries.assert_called()
    e.containerd.ensure_registry_configs.assert_called()

    # normal operation
    e.containerd.parse_registries.reset_mock()
    e.containerd.ensure_registry_configs.reset_mock()

    e.harness.update_config({"containerd_custom_registries": "fakeval"})
    e.containerd.parse_registries.assert_called_once_with("fakeval")
    e.containerd.ensure_registry_configs.assert_called_once_with(
        e.containerd.parse_registries.return_value
    )

    # no configuration
    e.containerd.parse_registries.reset_mock()
    e.containerd.ensure_registry_configs.reset_mock()
    e.containerd.parse_registries.return_value = []

    e.harness.update_config({"containerd_custom_registries": "fakeval2"})
    e.containerd.parse_registries.assert_called_once_with("fakeval2")
    e.containerd.ensure_registry_configs.assert_not_called()

    # exception
    e.containerd.parse_registries.reset_mock()
    e.containerd.ensure_registry_configs.reset_mock()

    e.containerd.parse_registries.side_effect = [ValueError("fake error")]

    e.harness.update_config({"containerd_custom_registries": "fakeval"})
    e.containerd.parse_registries.assert_called_once_with("fakeval")
    e.containerd.ensure_registry_configs.assert_not_called()
    assert e.harness.charm.unit.status.__class__ == BlockedStatus


@pytest.mark.parametrize("role", ["", "control-plane", "worker"])
@pytest.mark.parametrize("is_leader", [False, True])
@pytest.mark.parametrize("has_joined", [False, True])
def test_config_hostpath_storage(e: Environment, role: str, is_leader: bool, has_joined: bool):
    e.harness.update_config({"role": role})
    e.harness.set_leader(is_leader)
    e.harness.begin_with_initial_hooks()

    e.harness.charm._state.joined = has_joined
    e.microk8s.configure_hostpath_storage.reset_mock()

    # only the leader control plane unit enables
    e.harness.update_config({"hostpath_storage": True})
    if has_joined and is_leader and role != "worker":
        e.microk8s.configure_hostpath_storage.assert_called_once_with(True)
    else:
        e.microk8s.configure_hostpath_storage.assert_not_called()

    # only the leader control plane unit disables
    e.microk8s.configure_hostpath_storage.reset_mock()
    e.harness.update_config({"hostpath_storage": False})
    if has_joined and is_leader and role != "worker":
        e.microk8s.configure_hostpath_storage.assert_called_once_with(False)
    else:
        e.microk8s.configure_hostpath_storage.assert_not_called()


@pytest.mark.parametrize("role", ["", "control-plane", "worker"])
@pytest.mark.parametrize("is_leader", [False, True])
@pytest.mark.parametrize("has_joined", [False, True])
def test_config_rbac(e: Environment, role: str, is_leader: bool, has_joined: bool):
    e.harness.update_config({"role": role})
    e.harness.set_leader(is_leader)
    e.harness.begin_with_initial_hooks()

    e.harness.charm._state.joined = has_joined
    e.microk8s.configure_rbac.reset_mock()

    # only the leader control plane unit enables
    e.harness.update_config({"rbac": True})
    if role != "worker" and has_joined:
        e.microk8s.configure_rbac.assert_called_once_with(True)
    else:
        e.microk8s.configure_rbac.assert_not_called()

    # only the leader control plane unit disables
    e.microk8s.configure_rbac.reset_mock()
    e.harness.update_config({"rbac": False})
    if role != "worker" and has_joined:
        e.microk8s.configure_rbac.assert_called_once_with(False)
    else:
        e.microk8s.configure_rbac.assert_not_called()


@pytest.mark.parametrize("role", ["", "control-plane", "worker"])
@pytest.mark.parametrize("is_leader", [False, True])
@pytest.mark.parametrize("has_joined", [False, True])
def test_relation_dns(e: Environment, role: str, is_leader: bool, has_joined: bool):
    e.harness.update_config({"role": role})
    e.harness.set_leader(is_leader)
    e.harness.begin_with_initial_hooks()

    e.harness.charm._state.joined = has_joined
    e.microk8s.configure_dns.reset_mock()

    rel_id = e.harness.add_relation("dns", "coredns")
    e.harness.add_relation_unit(rel_id, "coredns/0")
    e.harness.update_relation_data(rel_id, "coredns/0", {"key": "value"})

    # no dns-ip and domain set yet
    e.microk8s.configure_dns.assert_not_called()

    # set dns-ip and domain, all joined units set
    e.harness.update_relation_data(
        rel_id, "coredns/0", {"sdn-ip": "fakeip", "domain": "fakedomain"}
    )
    if has_joined:
        e.microk8s.configure_dns.assert_called_once_with("fakeip", "fakedomain")
        assert e.harness.charm.unit.status == ops.model.ActiveStatus("fakestatus")
    else:
        e.microk8s.configure_dns.assert_not_called()
