# Copyright 2020 Paul Collins
# See LICENSE file for licensing details.

import json
import unittest

from unittest.mock import patch

from etchosts import (
    node_address_entries,
    refresh_etc_hosts,
)


NODES = {
    'items': [{
        'status': {
            'addresses': [
                {'type': 'Hostname', 'address': 'example.hostname'},
                {'type': 'InternalIP', 'address': '10.1.2.3'},
            ]
        }
    }]
}
EXPECTED_HOSTS = ['example.hostname']


class TestEtcHosts(unittest.TestCase):
    def test_node_address_entries(self):
        expected_entries = {'10.1.2.3': ['example.hostname']}
        self.assertEqual(node_address_entries(NODES), expected_entries)

    @patch('etchosts.read_etc_hosts')
    @patch('etchosts.sync_rename_sync')
    @patch('etchosts.write_temporary_file')
    def test_refresh_etc_hosts(self, _write, _sync, _read):
        _read.return_value = "\n".join([
            '127.0.0.1 localhost',
            '# This is a comment',
        ])
        expected_newlines = [
            '127.0.0.1 localhost',
            '# This is a comment',
            '10.1.2.3\texample.hostname',
        ]
        refresh_etc_hosts(json.dumps(NODES), EXPECTED_HOSTS)
        _write.assert_called_with('/etc/hosts', expected_newlines)
        # Confirm if we already have a hostname we don't add it again.
        _read.return_value += '\n10.1.2.3 example.hostname'
        refresh_etc_hosts(json.dumps(NODES), EXPECTED_HOSTS)
        _write.assert_called_with('/etc/hosts', expected_newlines)
