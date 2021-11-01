# Copyright 2020 Paul Collins
# See LICENSE file for licensing details.

import unittest
from unittest.mock import call, patch

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
    def test_begin_with_initial_hooks_on_leader(self, _check_call, _get, _patch):
        """The leader installs microk8s, enables addons, and opens ports."""
        _get.return_value.returncode = 0
        _get.return_value.stdout = b'{}'
        _patch.return_value.returncode = 0

        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()
        expected_subprocess_calls = [
            ['/usr/bin/apt-get', 'install', '--yes', 'nfs-common'],
            ['/usr/bin/snap', 'install', '--classic', 'microk8s'],
            ['/usr/sbin/addgroup', 'ubuntu', 'microk8s'],
            ['/usr/bin/snap', 'alias', 'microk8s.kubectl', 'kubectl'],
            ['open-port', '16443/tcp'],
            ['open-port', '80/tcp'],
            ['open-port', '443/tcp'],
            ['/snap/bin/microk8s', 'enable', 'dns', 'ingress'],
        ]
        self.assertEqual(len(expected_subprocess_calls), len(_check_call.call_args_list))
        for actual, expected in zip(_check_call.call_args_list, [call(c) for c in expected_subprocess_calls]):
            self.assertEqual(actual, expected)
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    @patch("kubectl.patch")
    @patch("kubectl.get")
    @patch("subprocess.check_call")
    def test_begin_with_initial_hooks_on_follower(self, _check_call, _get, _patch):
        """A follower installs microk8s and opens ports.  (A follower does not enable addons.)"""
        _get.return_value.returncode = 0
        _get.return_value.stdout = b'{}'
        _patch.return_value.returncode = 0

        self.harness.set_leader(False)
        self.harness.begin_with_initial_hooks()
        expected_subprocess_calls = [
            ['/usr/bin/apt-get', 'install', '--yes', 'nfs-common'],
            ['/usr/bin/snap', 'install', '--classic', 'microk8s'],
            ['/usr/sbin/addgroup', 'ubuntu', 'microk8s'],
            ['/usr/bin/snap', 'alias', 'microk8s.kubectl', 'kubectl'],
            ['open-port', '16443/tcp'],
            ['open-port', '80/tcp'],
            ['open-port', '443/tcp'],
        ]
        self.assertEqual(len(expected_subprocess_calls), len(_check_call.call_args_list))
        for actual, expected in zip(_check_call.call_args_list, [call(c) for c in expected_subprocess_calls]):
            self.assertEqual(actual, expected)
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    @patch("subprocess.check_call")
    def test_action_start(self, _check_call):
        self.harness.begin()
        self.harness.charm.cluster._microk8s_start(None)
        self.assertEqual(len(_check_call.call_args_list), 1)
        self.assertEqual(_check_call.call_args_list, [
            call(['/snap/bin/microk8s', 'start'])
        ])

    @patch("subprocess.check_call")
    def test_action_stop(self, _check_call):
        self.harness.begin()
        self.harness.charm.cluster._microk8s_stop(None)
        self.assertEqual(len(_check_call.call_args_list), 1)
        self.assertEqual(_check_call.call_args_list, [
            call(['/snap/bin/microk8s', 'stop'])
        ])

    @patch("subprocess.check_call")
    def test_action_status(self, _check_call):
        self.harness.begin()
        self.harness.charm.cluster._microk8s_status(None)
        self.assertEqual(len(_check_call.call_args_list), 1)
        self.assertEqual(_check_call.call_args_list, [
            call(['/snap/bin/microk8s', 'status'])
        ])
