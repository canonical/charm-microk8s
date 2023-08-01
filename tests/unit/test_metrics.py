#
# Copyright 2023 Canonical, Ltd.
#
import subprocess
from pathlib import Path
from unittest import mock

import pytest

import metrics


@mock.patch("util.ensure_call")
@mock.patch("util.charm_dir")
def test_apply_required_resources(charm_dir: mock.MagicMock, ensure_call: mock.MagicMock):
    charm_dir.return_value = Path("dir")
    metrics.apply_required_resources()

    assert ensure_call.mock_calls == [
        mock.call(["microk8s", "kubectl", "apply", "-f", "dir/src/deploy/metrics.yaml"]),
        mock.call(["microk8s", "kubectl", "apply", "-f", "dir/src/deploy/kube-state-metrics.yaml"]),
    ]


@mock.patch("util.run")
def test_get_tls_auth_existing_secret(run: mock.MagicMock):
    run.return_value.stdout = b'{"data": {"tls.crt": "ZmFrZWNydA==", "tls.key": "ZmFrZWtleQ=="}}'

    crt, key = metrics.get_tls_auth()
    assert crt == "fakecrt"
    assert key == "fakekey"

    run.assert_called_once_with(
        [
            "microk8s",
            "kubectl",
            "get",
            "secret",
            "--namespace=kube-system",
            "microk8s-observability-tls",
            "-o=json",
        ],
        capture_output=True,
    )


@mock.patch("util.ensure_call")
@mock.patch("util.run")
@mock.patch("util.charm_dir")
@mock.patch("microk8s.snap_data_dir")
def test_get_tls_auth_create_secret(
    snap_data_dir: mock.MagicMock,
    charm_dir: mock.MagicMock,
    run: mock.MagicMock,
    ensure_call: mock.MagicMock,
):
    snap_data_dir.return_value = Path("snapdatadir")
    charm_dir.return_value = Path("charmdir")
    run.side_effect = [
        subprocess.CalledProcessError(1, "fakeerr"),
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=b'{"data": {"tls.crt": "ZmFrZWNydA==", "tls.key": "ZmFrZWtleQ=="}}',
        ),
    ]

    ensure_call.side_effect = [
        None,
        subprocess.CompletedProcess(args=[], returncode=0, stdout=b"fakecsr"),
        None,
        None,
    ]

    crt, key = metrics.get_tls_auth()
    assert crt == "fakecrt"
    assert key == "fakekey"

    assert ensure_call.mock_calls == [
        mock.call(["openssl", "genrsa", "-out", "charmdir/metrics.key", "2048"]),
        mock.call(
            [
                "openssl",
                "req",
                "-new",
                "-subj",
                "/CN=system:serviceaccount:kube-system:microk8s-observability",
                "-key",
                "charmdir/metrics.key",
            ],
            capture_output=True,
        ),
        mock.call(
            [
                "openssl",
                "x509",
                "-req",
                "-sha256",
                "-CA",
                "snapdatadir/certs/ca.crt",
                "-CAkey",
                "snapdatadir/certs/ca.key",
                "-CAcreateserial",
                "-days",
                "3650",
                "-out",
                "charmdir/metrics.crt",
            ],
            input=b"fakecsr",
        ),
        mock.call(
            [
                "microk8s",
                "kubectl",
                "create",
                "secret",
                "tls",
                "microk8s-observability-tls",
                "--namespace=kube-system",
                "--cert",
                "charmdir/metrics.crt",
                "--key",
                "charmdir/metrics.key",
            ]
        ),
    ]


@pytest.mark.parametrize(
    "control_plane, expected_jobs",
    [
        (
            False,
            [
                {
                    "scheme": "https",
                    "tls_config": {
                        "insecure_skip_verify": True,
                        "cert": "fakecrt",
                        "key": "fakekey",
                    },
                    "job_name": "kube-proxy",
                    "static_configs": [{"targets": ["localhost:10250"]}],
                    "relabel_configs": [{"target_label": "job", "replacement": "kube-proxy"}],
                },
                {
                    "scheme": "https",
                    "tls_config": {
                        "insecure_skip_verify": True,
                        "cert": "fakecrt",
                        "key": "fakekey",
                    },
                    "job_name": "kubelet",
                    "metrics_path": "/metrics",
                    "static_configs": [
                        {"targets": ["localhost:10250"], "labels": {"node": "nodename"}}
                    ],
                    "relabel_configs": [
                        {"target_label": "metrics_path", "replacement": "/metrics"},
                        {"target_label": "job", "replacement": "kubelet"},
                    ],
                },
                {
                    "scheme": "https",
                    "tls_config": {
                        "insecure_skip_verify": True,
                        "cert": "fakecrt",
                        "key": "fakekey",
                    },
                    "job_name": "kubelet-cadvisor",
                    "metrics_path": "/metrics/cadvisor",
                    "static_configs": [
                        {"targets": ["localhost:10250"], "labels": {"node": "nodename"}}
                    ],
                    "relabel_configs": [
                        {"target_label": "metrics_path", "replacement": "/metrics/cadvisor"},
                        {"target_label": "job", "replacement": "kubelet"},
                    ],
                },
                {
                    "scheme": "https",
                    "tls_config": {
                        "insecure_skip_verify": True,
                        "cert": "fakecrt",
                        "key": "fakekey",
                    },
                    "job_name": "kubelet-probes",
                    "metrics_path": "/metrics/probes",
                    "static_configs": [
                        {"targets": ["localhost:10250"], "labels": {"node": "nodename"}}
                    ],
                    "relabel_configs": [
                        {"target_label": "metrics_path", "replacement": "/metrics/probes"},
                        {"target_label": "job", "replacement": "kubelet"},
                    ],
                },
            ],
        ),
        (
            True,
            [
                {
                    "scheme": "https",
                    "tls_config": {
                        "insecure_skip_verify": True,
                        "cert": "fakecrt",
                        "key": "fakekey",
                    },
                    "job_name": "apiserver",
                    "static_configs": [{"targets": ["localhost:16443"]}],
                    "relabel_configs": [{"target_label": "job", "replacement": "apiserver"}],
                },
                {
                    "scheme": "https",
                    "tls_config": {
                        "insecure_skip_verify": True,
                        "cert": "fakecrt",
                        "key": "fakekey",
                    },
                    "job_name": "kube-scheduler",
                    "static_configs": [{"targets": ["localhost:16443"]}],
                    "relabel_configs": [{"target_label": "job", "replacement": "kube-scheduler"}],
                },
                {
                    "scheme": "https",
                    "tls_config": {
                        "insecure_skip_verify": True,
                        "cert": "fakecrt",
                        "key": "fakekey",
                    },
                    "job_name": "kube-controller-manager",
                    "static_configs": [{"targets": ["localhost:16443"]}],
                    "relabel_configs": [
                        {"target_label": "job", "replacement": "kube-controller-manager"}
                    ],
                },
                {
                    "scheme": "https",
                    "tls_config": {
                        "insecure_skip_verify": True,
                        "cert": "fakecrt",
                        "key": "fakekey",
                    },
                    "job_name": "kube-state-metrics",
                    "static_configs": [{"targets": ["localhost:16443"]}],
                    "metrics_path": "/api/v1/namespaces/kube-system/services/kube-state-metrics:http-metrics/proxy/metrics",  # noqa
                    "relabel_configs": [
                        {"target_label": "job", "replacement": "kube-state-metrics"}
                    ],
                },
                {
                    "scheme": "https",
                    "tls_config": {
                        "insecure_skip_verify": True,
                        "cert": "fakecrt",
                        "key": "fakekey",
                    },
                    "job_name": "kube-proxy",
                    "static_configs": [{"targets": ["localhost:10250"]}],
                    "relabel_configs": [{"target_label": "job", "replacement": "kube-proxy"}],
                },
                {
                    "scheme": "https",
                    "tls_config": {
                        "insecure_skip_verify": True,
                        "cert": "fakecrt",
                        "key": "fakekey",
                    },
                    "job_name": "kubelet",
                    "metrics_path": "/metrics",
                    "static_configs": [
                        {"targets": ["localhost:10250"], "labels": {"node": "nodename"}}
                    ],
                    "relabel_configs": [
                        {"target_label": "metrics_path", "replacement": "/metrics"},
                        {"target_label": "job", "replacement": "kubelet"},
                    ],
                },
                {
                    "scheme": "https",
                    "tls_config": {
                        "insecure_skip_verify": True,
                        "cert": "fakecrt",
                        "key": "fakekey",
                    },
                    "job_name": "kubelet-cadvisor",
                    "metrics_path": "/metrics/cadvisor",
                    "static_configs": [
                        {"targets": ["localhost:10250"], "labels": {"node": "nodename"}}
                    ],
                    "relabel_configs": [
                        {"target_label": "metrics_path", "replacement": "/metrics/cadvisor"},
                        {"target_label": "job", "replacement": "kubelet"},
                    ],
                },
                {
                    "scheme": "https",
                    "tls_config": {
                        "insecure_skip_verify": True,
                        "cert": "fakecrt",
                        "key": "fakekey",
                    },
                    "job_name": "kubelet-probes",
                    "metrics_path": "/metrics/probes",
                    "static_configs": [
                        {"targets": ["localhost:10250"], "labels": {"node": "nodename"}}
                    ],
                    "relabel_configs": [
                        {"target_label": "metrics_path", "replacement": "/metrics/probes"},
                        {"target_label": "job", "replacement": "kubelet"},
                    ],
                },
            ],
        ),
    ],
)
def test_build_scrape_jobs(control_plane: bool, expected_jobs: list):
    assert (
        metrics.build_scrape_jobs("fakecrt", "fakekey", control_plane, "nodename") == expected_jobs
    )
