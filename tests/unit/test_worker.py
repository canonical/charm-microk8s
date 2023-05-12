# Copyright 2023 Angelos Kolaitis
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

from unittest import mock

import ops
import ops.testing
import pytest

from charm import MicroK8sCharm


@pytest.fixture
def harness():
    harness = ops.testing.Harness(MicroK8sCharm)
    yield harness
    harness.cleanup()


@mock.patch("subprocess.check_call")
def test_worker_install(_check_call, harness: ops.testing.Harness):
    harness.begin_with_initial_hooks()

    _check_call.assert_has_calls(
        [
            mock.call(["apt-get", "install", "--yes", "nfs-common"]),
            mock.call(["apt-get", "install", "--yes", "open-iscsi"]),
            mock.call(["apt-get", "install", "--yes", "linux-modules-extra-5.13.0-39-generic"]),
            mock.call(["snap", "install", "microk8s", "--classic"]),
        ]
    )

    assert harness.charm.model.unit.opened_ports() == {
        ops.model.OpenedPort(protocol="tcp", port=16443),
        ops.model.OpenedPort(protocol="tcp", port=80),
        ops.model.OpenedPort(protocol="tcp", port=443),
    }

    assert isinstance(harness.charm.model.unit.status, ops.model.WaitingStatus)


@mock.patch("subprocess.check_call")
@mock.patch("util.node_to_unit_status")
@mock.patch("socket.gethostname")
def test_worker_valid_relation(
    _get_hostname, _get_status, _check_call, harness: ops.testing.Harness
):
    _get_status.return_value = ops.model.ActiveStatus("mock status")
    _get_hostname.return_value = "fakehostname"

    harness.begin_with_initial_hooks()
    unit = harness.charm.model.unit
    assert isinstance(unit.status, ops.model.WaitingStatus)

    rel_id = harness.add_relation("microk8s", "microk8s")
    harness.add_relation_unit(rel_id, "microk8s/0")
    harness.update_relation_data(rel_id, "microk8s", {"join_url": "MOCK_JOIN_URL"})

    _check_call.assert_called_with(["microk8s", "join", "MOCK_JOIN_URL", "--worker"])
    _get_status.assert_called_once_with("fakehostname")
    assert unit.status == ops.model.ActiveStatus("mock status")
    assert harness.charm.model.get_relation("microk8s").data[unit]["hostname"] == "fakehostname"

    _check_call.reset_mock()

    harness.remove_relation_unit(rel_id, "microk8s/0")
    harness.remove_relation(rel_id)

    _check_call.assert_called_once_with(["microk8s", "leave"])
    assert isinstance(unit.status, ops.model.WaitingStatus)


@mock.patch("subprocess.check_call")
@mock.patch("util.node_to_unit_status")
def test_worker_invalid_relation(_get_status, _check_call, harness: ops.testing.Harness):
    _get_status.return_value = ops.model.ActiveStatus("mock status")

    harness.begin_with_initial_hooks()
    assert isinstance(harness.charm.model.unit.status, ops.model.WaitingStatus)

    _check_call.reset_mock()

    rel_id = harness.add_relation("microk8s", "microk8s")
    harness.add_relation_unit(rel_id, "microk8s/0")
    harness.update_relation_data(rel_id, "microk8s", {"not_a_join_url": "MOCK_JOIN_URL"})

    _check_call.assert_not_called()
    assert isinstance(harness.charm.model.unit.status, ops.model.WaitingStatus)
