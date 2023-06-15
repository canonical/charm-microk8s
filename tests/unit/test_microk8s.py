#
# Copyright 2023 Canonical, Ltd.
#
from pathlib import Path
from unittest import mock

import pytest
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus

import charm_config
import microk8s


@mock.patch("util.ensure_call")
def test_microk8s_install(ensure_call: mock.MagicMock):
    microk8s.install()
    ensure_call.assert_called_once_with(
        ["snap", "install", "microk8s", "--classic", "--channel", charm_config.SNAP_CHANNEL]
    )


@mock.patch("util.ensure_call")
def test_microk8s_upgrade(ensure_call: mock.MagicMock):
    microk8s.upgrade()
    ensure_call.assert_called_once_with(
        ["snap", "refresh", "microk8s", "--channel", charm_config.SNAP_CHANNEL]
    )


@mock.patch("util.ensure_call")
def test_microk8s_uninstall(ensure_call: mock.MagicMock):
    microk8s.uninstall()
    ensure_call.assert_called_once_with(["snap", "remove", "microk8s", "--purge"])


@mock.patch("util.ensure_call")
def test_microk8s_wait_ready(ensure_call: mock.MagicMock):
    microk8s.wait_ready(timeout=5)
    ensure_call.assert_called_once_with(["microk8s", "status", "--wait-ready", "--timeout=5"])


@mock.patch("util.ensure_call")
def test_microk8s_remove_node(ensure_call: mock.MagicMock):
    microk8s.remove_node("node-1")
    ensure_call.assert_called_once_with(["microk8s", "remove-node", "node-1", "--force"])


@mock.patch("util.ensure_call")
def test_microk8s_join(ensure_call: mock.MagicMock):
    join_url = "10.10.10.10:25000/01010101010101010101010101010101"

    microk8s.join(join_url, False)
    ensure_call.assert_called_once_with(["microk8s", "join", join_url])
    ensure_call.reset_mock()

    microk8s.join(join_url, True)
    ensure_call.assert_called_once_with(["microk8s", "join", join_url, "--worker"])


@mock.patch("util.ensure_call")
@mock.patch("os.urandom")
def test_microk8s_add_node(urandom: mock.MagicMock, ensure_call: mock.MagicMock):
    urandom.return_value = b"\x01" * 16

    token = microk8s.add_node()
    assert token == "01010101010101010101010101010101"
    urandom.assert_called_once_with(16)
    ensure_call.assert_called_once_with(
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


@mock.patch("microk8s.snap_data_dir", autospec=True)
@mock.patch("util.ensure_file", autospec=True)
@mock.patch("util.ensure_block", autospec=True)
@mock.patch("util.ensure_call", autospec=True)
@pytest.mark.parametrize("changed", (True, False))
@pytest.mark.parametrize("containerd_env_contents", ("", "ulimit -n 1000"))
def test_microk8s_set_containerd_proxy_options(
    ensure_call: mock.MagicMock,
    ensure_block: mock.MagicMock,
    ensure_file: mock.MagicMock,
    snap_data_dir: mock.MagicMock,
    changed: bool,
    containerd_env_contents: str,
    tmp_path: Path,
):
    ensure_file.return_value = changed
    snap_data_dir.return_value = tmp_path

    # initial contents
    (tmp_path / "args").mkdir()
    (tmp_path / "args" / "containerd-env").write_text(containerd_env_contents)

    # no change when empty
    microk8s.set_containerd_proxy_options("", "", "")
    ensure_file.assert_not_called()
    ensure_block.assert_not_called()
    ensure_call.assert_not_called()

    # change config and restart service if something changed
    microk8s.set_containerd_proxy_options("fake1", "fake2", "no-proxy")
    ensure_block.assert_called_once_with(
        containerd_env_contents,
        "http_proxy=fake1\nhttps_proxy=fake2\nno_proxy=no-proxy",
        "{mark} managed by microk8s charm",
    )
    ensure_file.assert_called_once_with(
        tmp_path / "args" / "containerd-env", ensure_block.return_value, 0o600, 0, 0
    )
    if changed:
        ensure_call.assert_called_once_with(["snap", "restart", "microk8s.daemon-containerd"])
    else:
        ensure_call.assert_not_called()


@mock.patch("microk8s.snap_data_dir")
@mock.patch("os.chown")
@mock.patch("os.chmod")
def test_microk8s_disable_cert_reissue(
    chmod: mock.MagicMock, chown: mock.MagicMock, snap_data_dir: mock.MagicMock, tmp_path: Path
):
    snap_data_dir.return_value = tmp_path

    # disable cert reissue, ensure lock file exists
    microk8s.disable_cert_reissue()
    chown.assert_called_once_with(tmp_path / "var" / "lock" / "no-cert-reissue", 0, 0)
    chmod.assert_called_once_with(tmp_path / "var" / "lock" / "no-cert-reissue", 0o600)
    assert (tmp_path / "var" / "lock" / "no-cert-reissue").exists()

    microk8s.disable_cert_reissue()
    assert (tmp_path / "var" / "lock" / "no-cert-reissue").exists()


@pytest.mark.parametrize(
    "config_str, extra_sans",
    [
        ("", []),
        (" ", []),
        ("1.1.1.1,k8s.local", ["1.1.1.1", "k8s.local"]),
        ("1.1.1.1,k8s.local,%UNIT_PUBLIC_ADDRESS%", ["1.1.1.1", "k8s.local", "2.2.2.2"]),
        ("1.1.1.1, 2.2.2.2", ["1.1.1.1", "2.2.2.2"]),
    ],
)
@mock.patch("microk8s.apply_launch_configuration", autospec=True)
@mock.patch("ops_helpers.get_unit_public_address", autospec=True)
def test_microk8s_configure_extra_sans(
    get_unit_public_address: mock.MagicMock,
    apply_launch_configuration: mock.MagicMock,
    config_str: str,
    extra_sans: list,
):
    get_unit_public_address.return_value = "2.2.2.2"

    # no change when empty
    microk8s.configure_extra_sans(config_str)
    apply_launch_configuration.assert_called_once_with({"extraSANs": extra_sans})


@mock.patch("util.ensure_call")
def test_microk8s_apply_launch_configuration(ensure_call: mock.MagicMock):
    microk8s.apply_launch_configuration({"key": "value"})

    ensure_call.assert_called_once_with(
        ["/snap/microk8s/current/bin/cluster-agent", "init", "--config-file", "-"],
        input=b'{"version": "0.1.0", "key": "value"}',
        env={
            "SNAP": "/snap/microk8s/current",
            "SNAP_DATA": "/var/snap/microk8s/current",
        },
    )


@pytest.mark.parametrize(
    "status, enable, expect_calls",
    [
        ("enabled", True, []),
        ("disabled", False, []),
        ("enabled", False, [mock.call(["microk8s", "disable", "hostpath-storage"], input=b"n")]),
        ("disabled", True, [mock.call(["microk8s", "enable", "hostpath-storage"])]),
    ],
)
@mock.patch("util.ensure_call")
def test_microk8s_configure_hostpath_storage(
    ensure_call: mock.MagicMock, status: str, enable: bool, expect_calls: list
):
    ensure_call.return_value.stdout = status.encode()

    microk8s.configure_hostpath_storage(enable)

    assert ensure_call.mock_calls == [
        mock.call(["microk8s", "status", "-a", "hostpath-storage"], capture_output=True),
        *expect_calls,
    ]
