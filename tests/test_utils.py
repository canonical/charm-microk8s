import unittest
from utils import join_url_from_add_node_output


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
