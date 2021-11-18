# Copyright 2020 Paul Collins
# See LICENSE file for licensing details.

import subprocess

import unittest
from unittest.mock import call, mock_open, patch, ANY


from ops.model import ActiveStatus
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
    @patch("builtins.open", new_callable=mock_open, read_data="")
    def test_begin_with_initial_hooks_on_leader(self, _open, _check_output, _check_call, _get, _patch):
        """The leader installs microk8s, enables addons, and opens ports."""
        _get.return_value.returncode = 0
        _get.return_value.stdout = b"{}"
        _patch.return_value.returncode = 0

        _check_output.side_effect = [b"1.1.1.1", b"2.2.2.2"]
        self.harness.update_config({"containerd_env": ""})

        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())
        self.assertEqual(
            _check_call.call_args_list,
            [
                call(["/usr/bin/apt-get", "install", "--yes", "nfs-common"]),
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
    @patch("builtins.open", new_callable=mock_open, read_data="")
    def test_begin_with_initial_hooks_on_follower(self, _open, _check_output, _check_call, _get, _patch):
        """A follower installs microk8s and opens ports.  (A follower does not enable addons.)"""
        _get.return_value.returncode = 0
        _get.return_value.stdout = b"{}"
        _patch.return_value.returncode = 0

        _check_output.side_effect = [b"1.1.1.1", b"2.2.2.2"]
        self.harness.update_config({"containerd_env": ""})

        self.harness.set_leader(False)
        self.harness.begin_with_initial_hooks()
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())
        self.assertEqual(
            _check_call.call_args_list,
            [
                call(["/usr/bin/apt-get", "install", "--yes", "nfs-common"]),
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
