#
# Copyright 2023 Canonical, Ltd.
#
from unittest import mock

import pytest
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus

import microk8s


@mock.patch("subprocess.check_call")
@pytest.mark.parametrize(
    "channel, command",
    [
        ("", ["snap", "install", "microk8s", "--classic"]),
        ("1.27/stable", ["snap", "install", "microk8s", "--classic", "--channel", "1.27/stable"]),
        ("1.27-strict", ["snap", "install", "microk8s", "--classic", "--channel", "1.27-strict"]),
    ],
)
def test_microk8s_install(check_call: mock.MagicMock, channel: str, command: list):
    microk8s.install(channel)
    check_call.assert_called_once_with(command)


@mock.patch("subprocess.check_call")
def test_microk8s_uninstall(check_call: mock.MagicMock):
    microk8s.uninstall()
    check_call.assert_called_once_with(["snap", "remove", "microk8s", "--purge"])


@mock.patch("subprocess.check_call")
def test_microk8s_wait_ready(check_call: mock.MagicMock):
    microk8s.wait_ready(timeout=5)
    check_call.assert_called_once_with(["microk8s", "status", "--wait-ready", "--timeout=5"])


@mock.patch("subprocess.check_call")
def test_microk8s_remove_node(check_call: mock.MagicMock):
    microk8s.remove_node("node-1")
    check_call.assert_called_once_with(["microk8s", "remove-node", "node-1", "--force"])


@mock.patch("subprocess.check_call")
def test_microk8s_join(check_call: mock.MagicMock):
    join_url = "10.10.10.10:25000/01010101010101010101010101010101"

    microk8s.join(join_url, False)
    check_call.assert_called_once_with(["microk8s", "join", join_url])
    check_call.reset_mock()

    microk8s.join(join_url, True)
    check_call.assert_called_once_with(["microk8s", "join", join_url, "--worker"])


@mock.patch("subprocess.check_call")
@mock.patch("os.urandom")
def test_microk8s_add_node(urandom: mock.MagicMock, check_call: mock.MagicMock):
    urandom.return_value = b"\x01" * 16

    token = microk8s.add_node()
    assert token == "01010101010101010101010101010101"
    urandom.assert_called_once_with(16)
    check_call.assert_called_once_with(
        ["microk8s", "add-node", "--token", token, "--token-ttl", "7200"]
    )


STATUS_MESSAGES = {
    "NOT_READY_STATUS": """
{
    "lastHeartbeatTime": "2023-05-12T05:54:05Z",
    "lastTransitionTime": "2023-05-12T05:54:05Z",
    "message": "[container runtime network not ready: NetworkReady=false reason:NetworkPluginNotReady message:Network plugin returns error: cni plugin not initialized, CSINode is not yet initialized]",
    "reason": "KubeletNotReady",
    "status": "False",
    "type": "Ready"
}
""",  # noqa
    "READY_STATUS": """
{
    "lastHeartbeatTime": "2023-05-12T05:54:22Z",
    "lastTransitionTime": "2023-05-12T05:54:22Z",
    "message": "kubelet is posting ready status. AppArmor enabled",
    "reason": "KubeletReady",
    "status": "True",
    "type": "Ready"
}
""",
    "INVALID_STATUS": """not a json message""",
}


@mock.patch("subprocess.check_output")
@pytest.mark.parametrize(
    "message, expect_status",
    [
        ("READY_STATUS", ActiveStatus("node is ready")),
        ("NOT_READY_STATUS", WaitingStatus("node is not ready: KubeletNotReady")),
        ("INVALID_STATUS", MaintenanceStatus("waiting for node")),
    ],
)
def test_microk8s_get_unit_status(check_output: mock.MagicMock, message: str, expect_status):
    check_output.return_value = STATUS_MESSAGES[message].encode()

    status = microk8s.get_unit_status("node-1")

    check_output.assert_called_once_with(
        [
            "/snap/microk8s/current/kubectl",
            "--kubeconfig=/var/snap/microk8s/current/credentials/kubelet.config",
            "get",
            "node",
            "node-1",
            "-o",
            "jsonpath={.status.conditions[?(@.type=='Ready')]}",
        ]
    )
    assert status == expect_status
