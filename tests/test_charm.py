import subprocess

import unittest
from unittest.mock import call, mock_open, patch, ANY, MagicMock


from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness
from charm import MicroK8sCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MicroK8sCharm)
        self.addCleanup(self.harness.cleanup)

    @patch("kubectl.patch")
    @patch("kubectl.get")
    @patch("subprocess.check_call")
    @patch("subprocess.check_output")
    @patch("os.uname")
    @patch("builtins.open", new_callable=mock_open, read_data="")
    def test_begin_with_initial_hooks_on_leader(self, _open, _uname, _check_output, _check_call, _get, _patch):
        """The leader installs microk8s, enables addons, and opens ports."""
        _get.return_value.returncode = 0
        _get.return_value.stdout = b"{}"
        _patch.return_value.returncode = 0

        _uname.return_value.release = "5.13"

        _check_output.side_effect = [b"1.1.1.1", b"2.2.2.2"]
        self.harness.update_config({"containerd_env": ""})

        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())
        self.assertEqual(
            _check_call.call_args_list,
            [
                call(["/usr/bin/apt-get", "install", "--yes", "nfs-common", "linux-modules-extra-5.13"]),
                call(["/usr/bin/snap", "install", "--classic", "microk8s"]),
                call(["/usr/sbin/addgroup", "ubuntu", "microk8s"]),
                call(["/usr/bin/snap", "alias", "microk8s.kubectl", "kubectl"]),
                call(["open-port", "16443/tcp"]),
                call(["open-port", "80/tcp"]),
                call(["open-port", "443/tcp"]),
                call(
                    ["/snap/bin/microk8s", "enable", "dns", "ingress"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
                ),
                call(["/usr/bin/snap", "set", "microk8s", ANY]),
            ],
        )
        self.assertEqual(
            _check_output.call_args_list,
            [
                call(["unit-get", "private-address"]),
                call(["unit-get", "public-address"]),
            ],
        )

    @patch("kubectl.patch")
    @patch("kubectl.get")
    @patch("subprocess.check_call")
    @patch("subprocess.check_output")
    @patch("os.uname")
    @patch("builtins.open", new_callable=mock_open, read_data="")
    def test_begin_with_initial_hooks_on_follower(self, _open, _uname, _check_output, _check_call, _get, _patch):
        """A follower installs microk8s and opens ports.  (A follower does not enable addons.)"""
        _get.return_value.returncode = 0
        _get.return_value.stdout = b"{}"
        _patch.return_value.returncode = 0

        _uname.return_value.release = "5.13"

        _check_output.side_effect = [b"1.1.1.1", b"2.2.2.2"]
        self.harness.update_config({"containerd_env": ""})

        self.harness.set_leader(False)
        self.harness.begin_with_initial_hooks()
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())
        self.assertEqual(
            _check_call.call_args_list,
            [
                call(["/usr/bin/apt-get", "install", "--yes", "nfs-common", "linux-modules-extra-5.13"]),
                call(["/usr/bin/snap", "install", "--classic", "microk8s"]),
                call(["/usr/sbin/addgroup", "ubuntu", "microk8s"]),
                call(["/usr/bin/snap", "alias", "microk8s.kubectl", "kubectl"]),
                call(["open-port", "16443/tcp"]),
                call(["open-port", "80/tcp"]),
                call(["open-port", "443/tcp"]),
                call(["/usr/bin/snap", "set", "microk8s", ANY]),
            ],
        )
        self.assertEqual(
            _check_output.call_args_list,
            [
                call(["unit-get", "private-address"]),
                call(["unit-get", "public-address"]),
            ],
        )

    @patch("subprocess.check_call")
    def test_action_start(self, _check_call):
        self.harness.begin()
        self.harness.charm.cluster._microk8s_start(None)
        self.assertEqual(len(_check_call.call_args_list), 1)
        self.assertEqual(_check_call.call_args_list, [call(["/snap/bin/microk8s", "start"])])

    @patch("subprocess.check_call")
    def test_action_stop(self, _check_call):
        self.harness.begin()
        self.harness.charm.cluster._microk8s_stop(None)
        self.assertEqual(len(_check_call.call_args_list), 1)
        self.assertEqual(_check_call.call_args_list, [call(["/snap/bin/microk8s", "stop"])])

    @patch("subprocess.check_call")
    def test_action_status(self, _check_call):
        self.harness.begin()
        self.harness.charm.cluster._microk8s_status(None)
        self.assertEqual(len(_check_call.call_args_list), 1)
        self.assertEqual(_check_call.call_args_list, [call(["/snap/bin/microk8s", "status"])])

    @patch("kubectl.patch")
    @patch("kubectl.get")
    @patch("subprocess.check_call")
    @patch("subprocess.check_output")
    def test_refresh_channel_prevent_downgrades(self, _check_output, _check_call, _get, _patch):
        _get.return_value.returncode = 0
        _get.return_value.stdout = b"{}"
        _patch.return_value.returncode = 0
        self.harness.begin()

        _check_output.return_value = b"tracking: '1.21'"

        self.harness.update_config({"channel": "1.20"})
        self.assertNotIn(call(["snap", "refresh", "microk8s", "--channel=1.20"]), _check_call.call_args_list)
        self.assertEqual(self.harness.charm.model.unit.status, BlockedStatus("preventing downgrade from 1.21 to 1.20"))

        self.harness.update_config({"channel": "1.22"})
        self.assertIn(call(["snap", "refresh", "microk8s", "--channel=1.22"]), _check_call.call_args_list)
        self.assertEqual(self.harness.charm.model.unit.status, ActiveStatus())

    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    @patch("yaml.dump")
    @patch("builtins.open", new_callable=mock_open, read_data="")
    def test_action_kubeconfig(self, _open, _yaml_dump, _check_call, _check_output):
        self.harness.begin()
        _check_output.side_effect = [b"clusters: [{cluster: {server: https://some-address:16443}}]", b"192.0.2.1"]

        event = MagicMock()
        self.harness.charm.cluster._microk8s_kubeconfig(event)
        self.assertEqual(
            _check_output.call_args_list,
            [call(["/snap/bin/microk8s", "config"]), call(["unit-get", "public-address"])],
        )
        self.assertEqual(_check_call.call_args_list, [call(["chown", "-R", "ubuntu:ubuntu", "/home/ubuntu/config"])])

        _yaml_dump.assert_called_once_with({"clusters": [{"cluster": {"server": "https://192.0.2.1:16443"}}]}, _open())

        event.set_results.assert_called_once_with({"kubeconfig": "/home/ubuntu/config"})

    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    @patch("yaml.dump")
    @patch("builtins.open", new_callable=mock_open, read_data="")
    def test_action_kubeconfig_ipv6(self, _open, _yaml_dump, _check_call, _check_output):
        self.harness.begin()
        _check_output.side_effect = [b"clusters: [{cluster: {server: https://some-address:16443}}]", b"2001:db8::1"]

        event = MagicMock()
        self.harness.charm.cluster._microk8s_kubeconfig(event)
        self.assertEqual(
            _check_output.call_args_list,
            [call(["/snap/bin/microk8s", "config"]), call(["unit-get", "public-address"])],
        )
        self.assertEqual(_check_call.call_args_list, [call(["chown", "-R", "ubuntu:ubuntu", "/home/ubuntu/config"])])

        _yaml_dump.assert_called_once_with(
            {"clusters": [{"cluster": {"server": "https://[2001:db8::1]:16443"}}]}, _open()
        )

        event.set_results.assert_called_once_with({"kubeconfig": "/home/ubuntu/config"})
