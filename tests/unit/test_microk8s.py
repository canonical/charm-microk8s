#
# Copyright 2023 Canonical, Ltd.
#
from pathlib import Path
from unittest import mock

import pytest
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus

import charm_config
import microk8s


@mock.patch("subprocess.check_call")
def test_microk8s_install(check_call: mock.MagicMock):
    microk8s.install()
    check_call.assert_called_once_with(
        ["snap", "install", "microk8s", "--classic", "--channel", charm_config.SNAP_CHANNEL]
    )


@mock.patch("subprocess.check_call")
def test_microk8s_upgrade(check_call: mock.MagicMock):
    microk8s.upgrade()
    check_call.assert_called_once_with(
        ["snap", "refresh", "microk8s", "--channel", charm_config.SNAP_CHANNEL]
    )


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


@mock.patch("microk8s.snap_data_dir", autospec=True)
@mock.patch("util.ensure_file", autospec=True)
@mock.patch("util.ensure_block", autospec=True)
@mock.patch("util.check_call", autospec=True)
@pytest.mark.parametrize("changed", (True, False))
@pytest.mark.parametrize("containerd_env_contents", ("", "ulimit -n 1000"))
def test_microk8s_set_containerd_proxy_options(
    check_call: mock.MagicMock,
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
    check_call.assert_not_called()

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
        check_call.assert_called_once_with(["snap", "restart", "microk8s.daemon-containerd"])
    else:
        check_call.assert_not_called()


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


@mock.patch("microk8s.snap_data_dir", autospec=True)
@mock.patch("util.ensure_file", autospec=True)
@mock.patch("util.ensure_block", autospec=True)
@mock.patch("util.check_call", autospec=True)
@mock.patch("ops_helpers.get_unit_public_address", autospec=True)
@pytest.mark.parametrize("changed", (True, False))
def test_microk8s_configure_extra_sans(
    get_unit_public_address: mock.MagicMock,
    check_call: mock.MagicMock,
    ensure_block: mock.MagicMock,
    ensure_file: mock.MagicMock,
    snap_data_dir: mock.MagicMock,
    changed: bool,
    tmp_path: Path,
):
    ensure_file.return_value = changed
    snap_data_dir.return_value = tmp_path
    get_unit_public_address.return_value = "2.2.2.2"

    # no change when empty
    microk8s.configure_extra_sans([])
    ensure_file.assert_not_called()
    ensure_block.assert_not_called()
    check_call.assert_not_called()
    get_unit_public_address.assert_not_called()

    # change config and restart service if something changed
    microk8s.configure_extra_sans("1.1.1.1,k8s.local")

    get_unit_public_address.assert_not_called()
    ensure_block.assert_called_once_with(
        "",
        "[ alt_names ]\nIP.1000 = 1.1.1.1\nDNS.1001 = k8s.local",
        "# {mark} managed by microk8s charm",
    )
    ensure_file.assert_called_once_with(
        tmp_path / "certs" / "csr.conf.template", ensure_block.return_value, 0o600, 0, 0
    )
    if changed:
        check_call.assert_called_once_with(["microk8s", "refresh-certs", "-e", "server.crt"])
    else:
        check_call.assert_not_called()

    ensure_block.reset_mock()

    # change config and pass unit public address
    microk8s.configure_extra_sans("1.1.1.1,k8s.local,%UNIT_PUBLIC_ADDRESS%")

    get_unit_public_address.assert_called_once_with()
    ensure_block.assert_called_once_with(
        "",
        "[ alt_names ]\nIP.1000 = 1.1.1.1\nDNS.1001 = k8s.local\nIP.1002 = 2.2.2.2",
        "# {mark} managed by microk8s charm",
    )
