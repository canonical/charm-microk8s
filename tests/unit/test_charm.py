#
# Copyright 2023 Canonical, Ltd.
#

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


@pytest.mark.parametrize("role", ["", "control-plane"])
@pytest.mark.parametrize("has_joined", [False, True])
def test_config_disable_cert_reissue(e: Environment, role: str, has_joined: bool):
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")

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
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")

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
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")

    e.harness.update_config({"role": role, "automatic_certificate_reissue": True})
    e.harness.begin_with_initial_hooks()

    e.harness.charm.on.upgrade_charm.emit()

    e.microk8s.upgrade.assert_called_once()


@pytest.mark.parametrize("role", ["", "control-plane"])
@pytest.mark.parametrize("has_joined", [False, True])
def test_config_containerd_custom_registries(e: Environment, role: str, has_joined: bool):
    e.microk8s.get_unit_status.return_value = ops.model.ActiveStatus("fakestatus")

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
    assert e.harness.charm.unit.status.__class__ == BlockedStatus
