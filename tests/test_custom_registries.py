from containerd_config import Registry, InvalidRegistriesError, update_tls_config
from pathlib import Path
import json
import pytest
import tempfile


@pytest.mark.parametrize(
    "registry_errors",
    [
        ("", "Failed to decode json string"),
        ("{}", "custom_registries is not a list"),
        ("[1]", "registry #0 is not in object form"),
        ("[{}]", "registry #0 missing required field url"),
        ('[{"url": 1}]', "registry #0 field url=1 is not a string"),
        ('[{"url": "", "host": 1}]', "registry #0 field host=1 is not a string"),
        (
            '[{"url": "", "insecure_skip_verify": "FALSE"}]',
            "registry #0 field insecure_skip_verify='FALSE' is not a boolean",
        ),
        (
            '[{"url": "", "insecure_skip_verify": true, "why-am-i-here": "abc"}]',
            "registry #0 field why-am-i-here may not be specified",
        ),
        (
            '[{"url": "https://docker.io"}, {"url": "https://docker.io"}]',
            "registry #1 defines docker.io more than once",
        ),
        ("[]", None),
    ],
    ids=[
        "Invalid JSON",
        "Not a List",
        "List Item not an object",
        "Missing required field",
        "Non-stringly typed url",
        "Non-stringly typed host",
        "Accidentally truthy",
        "Restricted field",
        "Duplicate host",
        "No errors",
    ],
)
def test_invalid_custom_registries(registry_errors):
    """Verify error status for invalid custom registries configurations."""
    registries, error = registry_errors
    if error is None:
        assert Registry.parse(registries) == []
    else:
        with pytest.raises(InvalidRegistriesError) as ie:
            assert Registry.parse(registries)
        assert str(ie.value) == error


def test_update_tls_config():
    """Verify merges of registries."""
    with tempfile.TemporaryDirectory() as tmp_path:
        config = [
            {"url": "my.registry:port", "username": "user", "password": "pass"},
            {
                "url": "my.other.registry",
                "ca_file": "aGVsbG8gd29ybGQgY2EtZmlsZQ==",
                "key_file": "aGVsbG8gd29ybGQga2V5LWZpbGU=",
                "cert_file": "abc",  # invalid base64 is ignored
            },
        ]
        registries = Registry.parse(json.dumps(config))
        ctxs = update_tls_config(registries, [], certs_path=tmp_path)
        with Path(tmp_path, "my.other.registry", "ca.crt").open() as f:
            assert f.read() == "hello world ca-file"
        with Path(tmp_path, "my.other.registry", "client.key").open() as f:
            assert f.read() == "hello world key-file"
        assert not Path(tmp_path, "my.other.registry", "client.cert").exists()

        for ctx in ctxs:
            assert ctx.url

        # Remove 'my.other.registry' from config
        config = [{"url": "my.registry:port", "username": "user", "password": "pass"}]
        new_registries = Registry.parse(json.dumps(config))
        ctxs = update_tls_config(new_registries, registries, certs_path=tmp_path)
        assert not Path(tmp_path, "my.other.registry", "ca.crt").exists()
        assert not Path(tmp_path, "my.other.registry", "client.key").exists()
        assert not Path(tmp_path, "my.other.registry", "client.cert").exists()


# @pytest.mark.parametrize("version", ("v1", "v2"))
# @pytest.mark.parametrize("gpu", ("off", "on"), ids=("gpu off", "gpu on"))
# @mock.patch("reactive.containerd.endpoint_from_flag")
# @mock.patch("reactive.containerd.config")
# @mock.patch("charms.layer.containerd.can_mount_cgroup2", mock.Mock(return_value=False))
# def test_custom_registries_render(mock_config, mock_endpoint_from_flag, gpu, version):
#     """Verify exact rendering of config.toml files in both v1 and v2 formats."""

#     class MockConfig(dict):
#         def changed(self, *_args, **_kwargs):
#             return False

#     def jinja_render(source, target, context):
#         env = jinja2.Environment(loader=jinja2.FileSystemLoader("templates"))
#         template = env.get_template(source)
#         with open(target, "w") as fp:
#             fp.write(template.render(context))

#     render.side_effect = jinja_render
#     config = mock_config.return_value = MockConfig(config_version=version, gpu_driver="auto", runtime="auto")
#     mock_endpoint_from_flag.return_value.get_sandbox_image.return_value = "sandbox-image"
#     flags = {
#         "containerd.nvidia.available": gpu == "on",
#     }
#     is_state.side_effect = lambda flag: flags[flag]
#     config["custom_registries"] = json.dumps(
#         [
#             {"url": "my.registry:port", "username": "user", "password": "pass"},
#             {"url": "my.other.registry", "insecure_skip_verify": True},
#         ]
#     )

#     with tempfile.TemporaryDirectory() as tmp_dir:
#         with mock.patch("reactive.containerd.CONFIG_DIRECTORY", tmp_dir):
#             containerd.config_changed()
#         f_name = f"nvidia-{gpu}-{version}-config.toml"
#         expected = pathlib.Path(__file__).parent / "test_custom_registries_render" / f_name
#         target = pathlib.Path(tmp_dir) / "config.toml"
#         assert list(target.open()) == list(expected.open())
