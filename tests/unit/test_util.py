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


@mock.patch("time.sleep")
@mock.patch("subprocess.check_call")
def test_ensure_call(check_call: mock.MagicMock, sleep: mock.MagicMock):
    # first time raises exception, second time succeeds
    check_call.side_effect = (subprocess.CalledProcessError(-1, "cmd"), None)

    util.ensure_call(["echo"], env={"KEY": "VALUE"})

    assert check_call.mock_calls == [
        mock.call(["echo"], env={"KEY": "VALUE"}),
        mock.call(["echo"], env={"KEY": "VALUE"}),
    ]
    sleep.assert_called_once_with(2)


@mock.patch("time.sleep")
def test_ensure_func(sleep: mock.MagicMock):
    m = mock.MagicMock()

    args = [1, 2, 3]
    kwargs = {"key": "value"}

    # other exceptions are raised
    m.side_effect = ValueError("some error")
    with pytest.raises(ValueError):
        util._ensure_func(m, args, kwargs, retry_on=KeyError, backoff=20)

    m.assert_called_once_with(*args, **kwargs)
    sleep.assert_not_called()

    # eventually succeeds (side effect raises 5 exceptions, then succeeds)
    m.reset_mock()
    m.side_effect = [ValueError("some error")] * 5 + [None]
    util._ensure_func(m, args, kwargs, retry_on=ValueError, backoff=20)
    assert m.mock_calls == [mock.call(*args, **kwargs)] * 6
    assert sleep.mock_calls == [mock.call(20)] * 5

    # exception is raised after max_retries
    sleep.reset_mock()
    m.reset_mock()
    m.side_effect = [ValueError("some error")] * 5
    with pytest.raises(ValueError):
        util._ensure_func(m, args, kwargs, retry_on=ValueError, max_retries=3, backoff=20)

    assert m.mock_calls == [mock.call(*args, **kwargs)] * 3
    assert sleep.mock_calls == [mock.call(20)] * 2
