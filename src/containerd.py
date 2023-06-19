#
# Copyright 2023 Canonical, Ltd.
#
import base64
import json
import logging
from pathlib import Path
from typing import List, Optional

import pydantic
import tomli_w
from urllib3.util import parse_url

import microk8s
import util

LOG = logging.getLogger(__name__)


class Registry(pydantic.BaseModel, extra=pydantic.Extra.forbid):
    # e.g. "https://registry-1.docker.io"
    url: pydantic.AnyHttpUrl

    # e.g. "docker.io", or "registry.example.com:32000"
    host: Optional[str] = None

    # authentication settings
    username: Optional[str] = None
    password: Optional[str] = None

    # TLS configuration
    ca_file: Optional[str] = None
    cert_file: Optional[str] = None
    key_file: Optional[str] = None
    skip_verify: Optional[bool] = None

    # misc configuration
    override_path: Optional[bool] = None

    def __init__(self, *args, **kwargs):
        super(Registry, self).__init__(*args, **kwargs)

        self.host = self.host or parse_url(self.url).netloc

    @pydantic.validator("ca_file")
    def parse_base64_ca_file(cls, v):
        return base64.b64decode(v.encode()).decode()

    @pydantic.validator("cert_file")
    def parse_base64_cert_file(cls, v):
        return base64.b64decode(v.encode()).decode()

    @pydantic.validator("key_file")
    def parse_base64_key_file(cls, v):
        return base64.b64decode(v.encode()).decode()

    def get_ca_file_path(self) -> Path:
        return microk8s.snap_data_dir() / "args" / "certs.d" / self.host / "ca.crt"

    def get_cert_file_path(self) -> Path:
        return microk8s.snap_data_dir() / "args" / "certs.d" / self.host / "client.crt"

    def get_key_file_path(self) -> Path:
        return microk8s.snap_data_dir() / "args" / "certs.d" / self.host / "client.key"

    def get_hosts_toml_path(self) -> Path:
        return microk8s.snap_data_dir() / "args" / "certs.d" / self.host / "hosts.toml"

    def get_auth_config(self):
        """return auth configuration for registry"""
        if not self.username or not self.password:
            return {}

        return {
            parse_url(self.url).netloc: {
                "auth": {"username": self.username, "password": self.password}
            }
        }

    def get_hosts_toml(self):
        """return data for hosts.toml file"""
        host_config = {"capabilities": ["pull", "resolve"]}
        if self.ca_file:
            host_config["ca"] = self.get_ca_file_path().as_posix()
        if self.cert_file and self.key_file:
            host_config["client"] = [
                [self.get_cert_file_path().as_posix(), self.get_key_file_path().as_posix()]
            ]
        elif self.cert_file:
            host_config["client"] = self.get_cert_file_path().as_posix()

        if self.skip_verify:
            host_config["skip_verify"] = True
        if self.override_path:
            host_config["override_path"] = True

        return {
            "server": self.url,
            "host": {self.url: host_config},
        }

    def ensure_certificates(self):
        """ensure client and ca certificates"""
        ca_file_path = self.get_ca_file_path()
        if self.ca_file:
            LOG.debug("Configure custom CA %s", ca_file_path)
            util.ensure_file(ca_file_path, self.ca_file, 0o600, 0, 0)
        else:
            ca_file_path.unlink(missing_ok=True)

        cert_file_path = self.get_cert_file_path()
        if self.cert_file:
            LOG.debug("Configure client certificate %s", cert_file_path)
            util.ensure_file(cert_file_path, self.cert_file, 0o600, 0, 0)
        else:
            cert_file_path.unlink(missing_ok=True)

        key_file_path = self.get_key_file_path()
        if self.key_file:
            LOG.debug("Configure client key %s", key_file_path)
            util.ensure_file(key_file_path, self.key_file, 0o600, 0, 0)
        else:
            key_file_path.unlink(missing_ok=True)


class RegistryConfigs(pydantic.BaseModel, extra=pydantic.Extra.forbid):
    registries: List[Registry]


def parse_registries(json_str: str) -> List[Registry]:
    """parse registry configurations from json string. Raises ValueError
    if configuration is not valid"""
    if not json_str:
        return []

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"not valid JSON: {e}") from e

    return RegistryConfigs(registries=parsed).registries


def ensure_registry_configs(registries: List[Registry]):
    """ensure containerd configuration files match the specified registries.
    restart containerd service if needed"""
    auth_config = {}
    for r in registries:
        LOG.info("Configure registry %s (%s)", r.host, r.url)

        r.ensure_certificates()
        util.ensure_file(r.get_hosts_toml_path(), tomli_w.dumps(r.get_hosts_toml()), 0o600, 0, 0)

        if r.username and r.password:
            LOG.debug("Configure username and password for %s (%s)", r.url, r.host)
            auth_config.update(**r.get_auth_config())

    if not auth_config:
        return

    registry_configs = {
        "plugins": {"io.containerd.grpc.v1.cri": {"registry": {"configs": auth_config}}}
    }

    containerd_toml_path = microk8s.snap_data_dir() / "args" / "containerd-template.toml"
    containerd_toml = containerd_toml_path.read_text() if containerd_toml_path.exists() else ""
    new_containerd_toml = util.ensure_block(
        containerd_toml, tomli_w.dumps(registry_configs), "# {mark} managed by microk8s charm"
    )
    if util.ensure_file(containerd_toml_path, new_containerd_toml, 0o600, 0, 0):
        LOG.info("Restart containerd to apply registry configurations")
        util.ensure_call(["snap", "restart", "microk8s.daemon-containerd"])
