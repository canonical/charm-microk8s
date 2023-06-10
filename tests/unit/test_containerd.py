#
# Copyright 2023 Canonical, Ltd.
#
from pathlib import Path
from unittest import mock

import pytest
import tomli

import containerd


@mock.patch("microk8s.snap_data_dir")
@pytest.mark.parametrize(
    "expected_host, config",
    [
        ("docker.io", {"url": "https://registry-1.docker.io", "host": "docker.io"}),
        ("docker.io", {"url": "https://registry-1.docker.io/", "host": "docker.io"}),
        ("quay.io", {"url": "https://quay.io"}),
        ("quay.io", {"url": "https://quay.io", "host": None}),
        ("quay.io", {"url": "https://quay.io/", "host": None}),
        ("custom:5000", {"url": "https://custom:5000/v2"}),
    ],
)
def test_registry_host(snap_data_dir: mock.MagicMock, config: dict, expected_host: str):
    snap_data_dir.return_value = Path("snap_data")
    r = containerd.Registry(**config)
    assert r.host == expected_host
    assert r.get_ca_file_path() == Path(f"snap_data/args/certs.d/{r.host}/ca.crt")
    assert r.get_cert_file_path() == Path(f"snap_data/args/certs.d/{r.host}/client.crt")
    assert r.get_key_file_path() == Path(f"snap_data/args/certs.d/{r.host}/client.key")
    assert r.get_hosts_toml_path() == Path(f"snap_data/args/certs.d/{r.host}/hosts.toml")


@mock.patch("microk8s.snap_data_dir")
@mock.patch("os.chown")
@mock.patch("os.chmod")
def test_registry_certificates(
    chmod: mock.MagicMock, chown: mock.MagicMock, snap_data_dir: mock.MagicMock
):
    snap_data_dir.return_value = Path("snap_data")
    r = containerd.Registry(
        url="https://fakeurl",
        ca_file="dGVzdDA=",
        cert_file="dGVzdDE=",
        key_file="dGVzdDI==",
    )
    assert r.ca_file == "test0"
    assert r.cert_file == "test1"
    assert r.key_file == "test2"

    r.ensure_certificates()

    assert chmod.mock_calls == [
        mock.call(r.get_ca_file_path(), 0o600),
        mock.call(r.get_cert_file_path(), 0o600),
        mock.call(r.get_key_file_path(), 0o600),
    ]
    assert chown.mock_calls == [
        mock.call(r.get_ca_file_path(), 0, 0),
        mock.call(r.get_cert_file_path(), 0, 0),
        mock.call(r.get_key_file_path(), 0, 0),
    ]
    assert r.get_ca_file_path().read_text() == "test0"
    assert r.get_cert_file_path().read_text() == "test1"
    assert r.get_key_file_path().read_text() == "test2"

    r.ca_file = None
    r.cert_file = None
    r.key_file = None

    r.ensure_certificates()
    assert not r.get_ca_file_path().exists()
    assert not r.get_cert_file_path().exists()
    assert not r.get_key_file_path().exists()


def test_registry_get_auth_config():
    assert containerd.Registry(
        url="https://fakeurl", username="user", password="pass"
    ).get_auth_config() == {"fakeurl": {"auth": {"username": "user", "password": "pass"}}}

    assert containerd.Registry(url="https://fakeurl").get_auth_config() == {}


@mock.patch("microk8s.snap_data_dir")
@pytest.mark.parametrize(
    "registry, hosts_toml",
    [
        (
            containerd.Registry(url="https://fakeurl"),
            {
                "server": "https://fakeurl",
                "host": {"https://fakeurl": {"capabilities": ["pull", "resolve"]}},
            },
        ),
        (
            containerd.Registry(url="https://fakeurl", host=None, ca_file="dGVzdA=="),
            {
                "server": "https://fakeurl",
                "host": {
                    "https://fakeurl": {
                        "capabilities": ["pull", "resolve"],
                        "ca": "snap_data/args/certs.d/fakeurl/ca.crt",
                    }
                },
            },
        ),
        (
            containerd.Registry(url="https://fakeurl", host=None, cert_file="dGVzdA=="),
            {
                "server": "https://fakeurl",
                "host": {
                    "https://fakeurl": {
                        "capabilities": ["pull", "resolve"],
                        "client": "snap_data/args/certs.d/fakeurl/client.crt",
                    }
                },
            },
        ),
        (
            containerd.Registry(
                url="https://fakeurl", host="fakeurl", key_file="dGVzdA==", cert_file="dGVzdA=="
            ),
            {
                "server": "https://fakeurl",
                "host": {
                    "https://fakeurl": {
                        "capabilities": ["pull", "resolve"],
                        "client": [
                            [
                                "snap_data/args/certs.d/fakeurl/client.crt",
                                "snap_data/args/certs.d/fakeurl/client.key",
                            ]
                        ],
                    }
                },
            },
        ),
        (
            containerd.Registry(
                url="https://fakeurl", host="fakeurl", override_path=True, skip_verify=True
            ),
            {
                "server": "https://fakeurl",
                "host": {
                    "https://fakeurl": {
                        "capabilities": ["pull", "resolve"],
                        "skip_verify": True,
                        "override_path": True,
                    }
                },
            },
        ),
    ],
)
def test_registry_get_hosts_toml(
    snap_data_dir: mock.MagicMock, registry: containerd.Registry, hosts_toml: dict
):
    snap_data_dir.return_value = Path("snap_data")
    assert registry.get_hosts_toml() == hosts_toml


@pytest.mark.parametrize(
    "config",
    [
        "not a json string",
        '{"url": "https://fakeurl"}',
        '[{"url": "not a url"}]',
        '[{"url": "https://fakeurl", "unknown field": "fake value"}]',
    ],
)
def test_parse_registries_exception(config: str):
    with pytest.raises(ValueError):
        containerd.parse_registries(config)


def test_parse_registries():
    assert containerd.parse_registries(
        '[{"url": "https://fakeurl"}, {"url": "https://quay.io", "skip_verify": true}]'
    ) == [
        containerd.Registry(url="https://fakeurl", host="fakeurl"),
        containerd.Registry(url="https://quay.io", host="quay.io", skip_verify=True),
    ]

    assert containerd.parse_registries("") == []


@mock.patch("microk8s.snap_data_dir")
@mock.patch("util.ensure_call")
@mock.patch("util.ensure_file")
@pytest.mark.parametrize("changed", [True, False])
def test_ensure_registry_configs_auth_config(
    ensure_file: mock.MagicMock,
    ensure_call: mock.MagicMock,
    snap_data_dir: mock.MagicMock,
    tmp_path: Path,
    changed: bool,
):
    snap_data_dir.return_value = tmp_path
    ensure_file.return_value = changed

    registries = [
        containerd.Registry(
            url="https://registry-1.docker.io",
            host="docker.io",
            username="fakeuser",
            password="fakepass",
        ),
        containerd.Registry(
            url="https://my.internal.registry",
            host="my.internal.registry",
            ca_file="dGVzdA==",
            cert_file="dGVzdA==",
            key_file="dGVzdA==",
            skip_verify=False,
        ),
        containerd.Registry(
            url="https://registry.aliyuncs.com/v2/google_containers",
            host="registry.k8s.io",
            skip_verify=True,
            override_path=True,
        ),
    ]

    containerd.ensure_registry_configs([])
    ensure_file.assert_not_called()
    ensure_call.assert_not_called()

    containerd.ensure_registry_configs(registries)

    assert ensure_file.mock_calls == [
        mock.call(registries[0].get_hosts_toml_path(), mock.ANY, 0o600, 0, 0),
        mock.call(registries[1].get_ca_file_path(), mock.ANY, 0o600, 0, 0),
        mock.call(registries[1].get_cert_file_path(), mock.ANY, 0o600, 0, 0),
        mock.call(registries[1].get_key_file_path(), mock.ANY, 0o600, 0, 0),
        mock.call(registries[1].get_hosts_toml_path(), mock.ANY, 0o600, 0, 0),
        mock.call(registries[2].get_hosts_toml_path(), mock.ANY, 0o600, 0, 0),
        mock.call(tmp_path / "args" / "containerd-template.toml", mock.ANY, 0o600, 0, 0),
    ]

    containerd_toml = tomli.loads(ensure_file.mock_calls[6].args[1])
    assert containerd_toml["plugins"]["io.containerd.grpc.v1.cri"]["registry"]["configs"] == {
        "registry-1.docker.io": {
            "auth": {
                "username": "fakeuser",
                "password": "fakepass",
            },
        },
    }

    if changed:
        ensure_call.assert_called_once_with(["snap", "restart", "microk8s.daemon-containerd"])
    else:
        ensure_call.assert_not_called()
