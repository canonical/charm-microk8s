# Copyright 2020 Paul Collins
# See LICENSE file for licensing details.

import unittest
from unittest.mock import call, patch

from ops.model import ActiveStatus
from ops.testing import Harness
from charm import MicroK8sCharm


class TestCharm(unittest.TestCase):
    @patch("subprocess.check_call")
    def test_begin_with_initial_hooks_on_leader(self, _check_call):
        """The leader installs microk8s, enables addons, and opens ports."""
        harness = Harness(MicroK8sCharm)
        self.addCleanup(harness.cleanup)

        harness.set_leader(True)
        harness.begin_with_initial_hooks()
        expected_subprocess_calls = [
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
        self.assertEqual(harness.charm.unit.status, ActiveStatus())

    @patch("subprocess.check_call")
    def test_begin_with_initial_hooks_on_follower(self, _check_call):
        """A follower installs microk8s and opens ports.  (A follower does not enable addons.)"""
        harness = Harness(MicroK8sCharm)
        self.addCleanup(harness.cleanup)

        harness.set_leader(False)
        harness.begin_with_initial_hooks()
        expected_subprocess_calls = [
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
        self.assertEqual(harness.charm.unit.status, ActiveStatus())
