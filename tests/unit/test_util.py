#
# Copyright 2023 Canonical, Ltd.
#
import subprocess
from pathlib import Path
from unittest import mock

import pytest

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


@mock.patch("os.chown")
@mock.patch("os.chmod")
def test_ensure_file(chmod: mock.MagicMock, chown: mock.MagicMock, tmp_path: Path):
    # test create dir and then file
    changed = util.ensure_file(tmp_path / "a" / "b" / "file", "test", None, None, None)
    assert Path(tmp_path / "a" / "b").is_dir()
    assert Path(tmp_path / "a" / "b" / "file").read_text() == "test", "failed to write file"
    assert changed, "creating a file that does not exist previously should return True"
    chmod.assert_not_called()
    chown.assert_not_called()

    # test create file
    changed = util.ensure_file(tmp_path / "file", "faketext", 0o400, 0, 1000)
    assert Path(tmp_path / "file").read_text() == "faketext", "failed to write file"
    assert changed, "creating a file that does not exist previously should return True"
    chmod.assert_called_with(tmp_path / "file", 0o400)
    chown.assert_called_with(tmp_path / "file", 0, 1000)

    # test overwrite file with same contents
    changed = util.ensure_file(tmp_path / "file", "faketext", 0o600, 1000, 1001)
    assert Path(tmp_path / "file").read_text() == "faketext", "contents should not change"
    assert not changed, "file must not have changed"

    # test overwrite file with new contents
    changed = util.ensure_file(tmp_path / "file", "faketext2", 0o400, 1000, 1000)
    assert Path(tmp_path / "file").read_text() == "faketext2", "contents should change"
    assert changed, "file must have changed"

    # test chown and chmod file
    changed = util.ensure_file(tmp_path / "file", "faketext2", 0o600, 1000, 1001)
    assert Path(tmp_path / "file").read_text() == "faketext2", "contents should not change"
    assert not changed, "file has not changed if permissions change"
    chmod.assert_called_with(tmp_path / "file", 0o600)
    chown.assert_called_with(tmp_path / "file", 1000, 1001)


@pytest.mark.parametrize(
    "name, text, block, mark, expected",
    [
        (
            "add to end of file if missing",
            "l1\nl2",
            "myblock",
            "# {mark} block",
            "l1\nl2\n# begin block\nmyblock\n# end block\n",
        ),
        (
            "change existing block",
            "l1\n# begin\nl2\n# end\n",
            "l2\nl3",
            "# {mark}",
            "l1\n# begin\nl2\nl3\n# end\n",
        ),
        (
            "change existing block and preserve data afterwards",
            "l1\n# begin\nl2\n# end\nl4\nl5",
            "l2\nl3",
            "# {mark}",
            "l1\n# begin\nl2\nl3\n# end\nl4\nl5",
        ),
    ],
)
def test_ensure_block(name: str, text: str, block: str, mark: str, expected: list):
    _ = name
    assert util.ensure_block(text, block, mark) == expected
