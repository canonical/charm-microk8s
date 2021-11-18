# Copyright 2020 Paul Collins
# See LICENSE file for licensing details.

import unittest
from utils import check_kubernetes_version_is_older, join_url_from_add_node_output, get_kubernetes_version_from_channel


class TestUtils(unittest.TestCase):
    def test_join_url_from_add_node_output(self):
        output = "\n".join(
            [
                "microk8s join this",
                " microk8s join notthis",
                "#microk8s join nothiseither",
                "microk8s join that",
            ]
        )
        expected = "this"
        self.assertEqual(join_url_from_add_node_output(output), expected)
        # Ordering matters, return the first from the list.
        output = "\n".join(
            [
                "microk8s join that",
                "microk8s join this",
            ]
        )
        expected = "that"
        self.assertEqual(join_url_from_add_node_output(output), expected)

    def test_get_kubernetes_version_from_channel(self):
        for channel, result in [
            ("1.20", [1, 20]),
            ("1.21/stable", [1, 21]),
            ("1.22/latest/edge", [1, 22]),
        ]:
            self.assertEqual(get_kubernetes_version_from_channel(channel), result)

        for channel in ["", "latest", "latest/stable", "latest/edge/branch"]:
            with self.assertRaises((TypeError, ValueError)):
                get_kubernetes_version_from_channel(channel)

    def test_check_kubernetes_version_is_older(self):
        for current, new, result in [
            ("1.20", "1.21", False),
            ("1.20", "1.20", False),
            ("1.20", "1.20/stable/branch", False),
            ("latest", "1.20/stable/branch", False),
            ("1.21", "1.20/stable/branch", True),
            ("1.20", "latest", False),
            ("1.9", "1.10", False),
            ("latest/stable", "latest/edge/worker", False),
            ("latest/edge/worker", "latest/stable", False),
        ]:
            self.assertEqual(check_kubernetes_version_is_older(current, new), result)
