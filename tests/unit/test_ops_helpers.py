#
# Copyright 2023 Canonical, Ltd.
#
import subprocess
from unittest import mock

import ops_helpers


@mock.patch("subprocess.check_output")
def test_get_unit_public_address(check_output: mock.MagicMock):
    check_output.return_value = b"fakeaddr"

    assert ops_helpers.get_unit_public_address() == "fakeaddr"
    check_output.assert_called_once_with(["unit-get", "public-address"])


@mock.patch("subprocess.check_output")
def test_get_unit_public_address_exception(check_output: mock.MagicMock):
    check_output.side_effect = subprocess.CalledProcessError(1, "fakecmd")

    assert ops_helpers.get_unit_public_address() == "127.0.0.1"
