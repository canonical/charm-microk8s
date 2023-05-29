#
# Copyright 2023 Canonical, Ltd.
#
import subprocess
from unittest import mock

import util


@mock.patch("os.uname")
@mock.patch("subprocess.check_call")
def test_install_required_packages(check_call: mock.MagicMock, uname: mock.MagicMock):
    uname.return_value.release = "fakerelease"
    util.install_required_packages()

    assert check_call.mock_calls == [
        mock.call(["apt-get", "install", "--yes", "nfs-common"]),
        mock.call(["apt-get", "install", "--yes", "open-iscsi"]),
        mock.call(["apt-get", "install", "--yes", "linux-modules-extra-fakerelease"]),
    ]


@mock.patch("os.uname")
@mock.patch("subprocess.check_call")
def test_install_required_packages_exceptions(check_call: mock.MagicMock, uname: mock.MagicMock):
    uname.side_effect = OSError("fake exception")
    check_call.side_effect = subprocess.CalledProcessError(-1, "fake exception")

    util.install_required_packages()

    assert check_call.mock_calls == [
        mock.call(["apt-get", "install", "--yes", "nfs-common"]),
        mock.call(["apt-get", "install", "--yes", "open-iscsi"]),
    ]
