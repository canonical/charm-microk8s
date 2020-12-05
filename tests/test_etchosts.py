# Copyright 2020 Paul Collins
# See LICENSE file for licensing details.

import unittest
from etchosts import (
    node_address_entries,
    update_hosts_with,
)


class TestEtcHosts(unittest.TestCase):
    def test_node_address_entries(self):
        nodes = {'items': [
            {'status': {
                'addresses': [
                    {'type': 'Hostname', 'address': 'example.hostname'},
                    {'type': 'InternalIP', 'address': '10.1.2.3'},
                ]}}
        ]}
        expected_entries = {'10.1.2.3': ['example.hostname']}
        self.assertEqual(node_address_entries(nodes), expected_entries)

    def test_update_hosts_with(self):
        hosts = "\n".join([
            '127.0.0.1 localhost',
            '# This is a comment',
        ])
        entries = {'10.1.2.3': ['example.hostname']}
        expected_newlines = [
            '127.0.0.1 localhost',
            '# This is a comment',
            '10.1.2.3\texample.hostname',
        ]
        self.assertEqual(update_hosts_with(hosts, entries), expected_newlines)
        # Confirm if we already have a hostname we don't add it again.
        hosts += ('\n10.1.2.3 example.hostname')
        self.assertEqual(update_hosts_with(hosts, entries), expected_newlines)
