#
# Copyright 2023 Canonical, Ltd.
#
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


@mock.patch("util.ensure_call")
def test_get_bearer_token(ensure_call: mock.MagicMock):
    ensure_call.return_value.stdout = b"faketoken\n"

    token = metrics.get_bearer_token()
    assert token == "faketoken"

    ensure_call.assert_called_once_with(
        [
            "microk8s",
            "kubectl",
            "create",
            "token",
            "--namespace=kube-system",
            "microk8s-observability",
        ],
        capture_output=True,
    )


@pytest.mark.parametrize(
    "control_plane, expected_jobs",
    [
        (
            False,
            [
                {
                    "scheme": "https",
                    "tls_config": {"insecure_skip_verify": True},
                    "authorization": {"credentials": "faketoken"},
                    "job_name": "kube-proxy",
                    "static_configs": [{"targets": ["localhost:10250"]}],
                    "relabel_configs": [{"target_label": "job", "replacement": "kube-proxy"}],
                },
                {
                    "scheme": "https",
                    "tls_config": {"insecure_skip_verify": True},
                    "authorization": {"credentials": "faketoken"},
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
                    "tls_config": {"insecure_skip_verify": True},
                    "authorization": {"credentials": "faketoken"},
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
                    "tls_config": {"insecure_skip_verify": True},
                    "authorization": {"credentials": "faketoken"},
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
                    "tls_config": {"insecure_skip_verify": True},
                    "authorization": {"credentials": "faketoken"},
                    "job_name": "apiserver",
                    "static_configs": [{"targets": ["localhost:16443"]}],
                    "relabel_configs": [{"target_label": "job", "replacement": "apiserver"}],
                },
                {
                    "scheme": "https",
                    "tls_config": {"insecure_skip_verify": True},
                    "authorization": {"credentials": "faketoken"},
                    "job_name": "kube-scheduler",
                    "static_configs": [{"targets": ["localhost:16443"]}],
                    "relabel_configs": [{"target_label": "job", "replacement": "kube-scheduler"}],
                },
                {
                    "scheme": "https",
                    "tls_config": {"insecure_skip_verify": True},
                    "authorization": {"credentials": "faketoken"},
                    "job_name": "kube-controller-manager",
                    "static_configs": [{"targets": ["localhost:16443"]}],
                    "relabel_configs": [
                        {"target_label": "job", "replacement": "kube-controller-manager"}
                    ],
                },
                {
                    "scheme": "https",
                    "tls_config": {"insecure_skip_verify": True},
                    "authorization": {"credentials": "faketoken"},
                    "job_name": "kube-state-metrics",
                    "static_configs": [{"targets": ["localhost:16443"]}],
                    "metrics_path": "/api/v1/namespaces/kube-system/services/kube-state-metrics:http-metrics/proxy/metrics",  # noqa
                    "relabel_configs": [
                        {"target_label": "job", "replacement": "kube-state-metrics"}
                    ],
                },
                {
                    "scheme": "https",
                    "tls_config": {"insecure_skip_verify": True},
                    "authorization": {"credentials": "faketoken"},
                    "job_name": "kube-proxy",
                    "static_configs": [{"targets": ["localhost:10250"]}],
                    "relabel_configs": [{"target_label": "job", "replacement": "kube-proxy"}],
                },
                {
                    "scheme": "https",
                    "tls_config": {"insecure_skip_verify": True},
                    "authorization": {"credentials": "faketoken"},
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
                    "tls_config": {"insecure_skip_verify": True},
                    "authorization": {"credentials": "faketoken"},
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
                    "tls_config": {"insecure_skip_verify": True},
                    "authorization": {"credentials": "faketoken"},
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
    assert metrics.build_scrape_jobs("faketoken", control_plane, "nodename") == expected_jobs
