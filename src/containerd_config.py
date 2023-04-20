from dataclasses import dataclass, field
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from typing import List, Optional
import base64
import binascii
import logging
import json

log = logging.getLogger(__name__)

CONTAINERD_CONFIG_TOML_PATH = "/var/snap/microk8s/current/args/containerd-template.toml"
CERTS_PATH = "/var/snap/microk8s/current/args/certs.d/"


def _strip_url(url):
    """Strip the URL of protocol, slashes etc., and keep host:port.

    Examples:
        url: http://10.10.10.10:8000 --> return: 10.10.10.10:8000
        url: https://myregistry.io:8000/ --> return: myregistry.io:8000
        url: myregistry.io:8000 --> return: myregistry.io:8000
    """
    return url.rstrip("/").split(sep="://", maxsplit=1)[-1]


def _registries_list(registries, default=None):
    """
    Parse registry config and ensure it returns a list

    :param str registries: representation of registries
    :param default: if provided, return rather than raising exceptions
    :return: List of registry dicts
    """
    try:
        registry_list = json.loads(registries)
    except json.JSONDecodeError:
        if default is None:
            raise

    if not isinstance(registry_list, list):
        if default is None:
            raise TypeError(f'registries must be a list (not "{type(registry_list)}")')
        registry_list = default

    return registry_list


class InvalidRegistriesError(Exception):
    """Error for Invalid Registry decoding."""


def update_tls_config(current: List["Registry"], previous: List["Registry"]) -> List["Registry"]:
    """
    Read registries config and remove old/write new tls files from/to disk.

    :param List previous: old juju config for custom registries
    :return: None
    """
    filenames = {"ca": "ca.crt", "key": "client.key", "cert": "client.cert"}
    # Remove tls files of old registries; so not to leave uneeded, stale files.
    for registry in previous:
        for filename in filenames.values():
            Path(CERTS_PATH, registry.host, filename).unlink(missing_ok=True)

    # Write tls files of new registries.
    for registry in current:
        for attr, filename in filenames.items():
            file_b64 = getattr(registry, f"{attr}_file", None)
            if file_b64:
                try:
                    file_contents = base64.b64decode(file_b64)
                except (binascii.Error, TypeError):
                    log.exception(f"{registry.url}:{attr} didn't look like base64 data... skipping")
                    continue
                tls_file = Path(CERTS_PATH, registry.host, filename)
                with open(tls_file, "wb") as f:
                    f.write(file_contents)
                setattr(registry, attr, f"${{SNAP_DATA}}/{tls_file.name}")
    return current


@dataclass
class Registry:
    url: str
    host: str = field(init=False)
    username: Optional[str] = field(repr=False, init=False)
    password: Optional[str] = field(repr=False, init=False)
    ca_file: Optional[str] = field(repr=False, init=False)
    cert_file: Optional[str] = field(repr=False, init=False)
    key_file: Optional[str] = field(repr=False, init=False)
    insecure_skip_verify: Optional[bool] = field(repr=False, init=False)

    def __post_init__(self):
        """Populates host field from url if missing from registry.

        Examples:
            url: http://10.10.10.10:8000 --> host: 10.10.10.10:8000
            url: https://myregistry.io:8000/ --> host: myregistry.io:8000
            url: myregistry.io:8000 --> host: myregistry.io:8000
        """
        self.host = _strip_url(self.url)

    @classmethod
    def parse(cls, json_config) -> List["Registry"]:
        """
        Validate custom registries from config.

        :param str custom_registries: juju config for custom registries
        :return: error string for blocked status if condition exists, None otherwise
        :rtype: Optional[str]
        """
        try:
            registries = _registries_list(json_config)
        except json.JSONDecodeError as err:
            raise InvalidRegistriesError("Failed to decode json string") from err
        except TypeError as err:
            raise InvalidRegistriesError("custom_registries is not a list") from err

        required_fields = ["url"]
        str_fields = [
            "url",
            "host",
            "username",
            "password",
            "ca_file",
            "cert_file",
            "key_file",
        ]
        truthy_fields = [
            "insecure_skip_verify",
        ]
        host_set = set()
        all_registries = []
        for idx, reg in enumerate(registries):
            if not isinstance(reg, dict):
                raise InvalidRegistriesError(f"registry #{idx} is not in object form")
            for f in required_fields:
                if f not in reg:
                    raise InvalidRegistriesError(f"registry #{idx} missing required field {f}")
            registry = cls(reg["url"])
            for f in str_fields:
                value = reg.get(f)
                if value and not isinstance(value, str):
                    raise InvalidRegistriesError(f"registry #{idx} field {f}={value} is not a string")
                setattr(registry, f, value)
            for f in truthy_fields:
                value = reg.get(f)
                if f in reg and not isinstance(value, bool):
                    raise InvalidRegistriesError(f"registry #{idx} field {f}='{value}' is not a boolean")
                setattr(registry, f, value)
            for f in reg:
                if f not in str_fields + truthy_fields:
                    raise InvalidRegistriesError(f"registry #{idx} field {f} may not be specified")

            if registry.host in host_set:
                raise InvalidRegistriesError(f"registry #{idx} defines {registry.host} more than once")
            host_set.add(registry.host)
            all_registries.append(registry)
        return all_registries


class ContainerdConfig:
    template_path: Path = Path(CONTAINERD_CONFIG_TOML_PATH)

    def __init__(self, registries: List[Registry]):
        self.registries = registries

    def apply(self):
        templates = Path("templates/registries.toml")
        env = Environment(loader=FileSystemLoader("/"))
        context = {"custom_registries": self.registries}
        extend = env.get_template(str(templates.resolve())).render(context)

        toggle, excluded_charm_generated = True, []
        with Path(CONTAINERD_CONFIG_TOML_PATH).open() as toml_path:
            for line in toml_path:
                autogenerated = line.startswith("# !!! autogenerated.charm")
                toggle ^= autogenerated
                if toggle and not autogenerated:
                    excluded_charm_generated.append(line)
        with Path(CONTAINERD_CONFIG_TOML_PATH).open("w") as toml_path:
            toml_path.writelines(excluded_charm_generated)
            toml_path.write("\n" + extend.strip() + "\n")
