#
# Copyright 2023 Canonical, Ltd.
#


import json
import logging
import subprocess
from base64 import b64decode
from typing import Dict, List, Tuple

import microk8s
import util

LOG = logging.getLogger(__name__)


def apply_required_resources():
    """kubectl apply manifests that create the required roles and RBAC rules for observability"""
    for file in ["metrics.yaml", "kube-state-metrics.yaml"]:
        path = util.charm_dir() / "src" / "deploy" / file
        util.ensure_call(["microk8s", "kubectl", "apply", "-f", path.as_posix()])


def get_tls_auth() -> Tuple[str, str]:
    """return (cert, key) to use for TLS client auth on the metrics endpoints"""
    try:
        p = util.run(
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
        output = json.loads(p.stdout)["data"]
        return (b64decode(output["tls.crt"]).decode(), b64decode(output["tls.key"]).decode())

    except (json.JSONDecodeError, KeyError, TypeError, ValueError, subprocess.CalledProcessError):
        # could not retrieve secret, or it contains invalid data. create it

        LOG.info("Creating TLS auth for ServiceAccount microk8s-observability")

        key_path = util.charm_dir() / "metrics.key"
        crt_path = util.charm_dir() / "metrics.crt"

        # private key
        util.ensure_call(["openssl", "genrsa", "-out", key_path.as_posix(), "2048"])

        # csr
        p = util.ensure_call(
            [
                "openssl",
                "req",
                "-new",
                "-subj",
                "/CN=system:serviceaccount:kube-system:microk8s-observability",
                "-key",
                key_path.as_posix(),
            ],
            capture_output=True,
        )
        csr = p.stdout

        # sign certificate
        util.ensure_call(
            [
                "openssl",
                "x509",
                "-req",
                "-sha256",
                "-CA",
                (microk8s.snap_data_dir() / "certs" / "ca.crt").as_posix(),
                "-CAkey",
                (microk8s.snap_data_dir() / "certs" / "ca.key").as_posix(),
                "-CAcreateserial",
                "-days",
                "3650",
                "-out",
                crt_path.as_posix(),
            ],
            input=csr,
        )

        # create Kubernetes secret
        util.ensure_call(
            [
                "microk8s",
                "kubectl",
                "create",
                "secret",
                "tls",
                "microk8s-observability-tls",
                "--namespace=kube-system",
                "--cert",
                crt_path.as_posix(),
                "--key",
                key_path.as_posix(),
            ]
        )

        return get_tls_auth()


def build_scrape_jobs(cert: str, key: str, control_plane: bool, hostname: str) -> List[Dict]:
    """build scrape jobs for worker nodes (kubelet and kube-proxy)"""
    base_job = {
        "scheme": "https",
        "tls_config": {
            "insecure_skip_verify": True,
            "cert": cert,
            "key": key,
        },
    }

    scrape_jobs = []

    if control_plane:
        # apiserver, kube-scheduler, kube-controller-manager
        for job_name in ["apiserver", "kube-scheduler", "kube-controller-manager"]:
            scrape_jobs.append(
                {
                    **base_job,
                    "job_name": job_name,
                    "static_configs": [{"targets": ["localhost:16443"]}],
                    "relabel_configs": [{"target_label": "job", "replacement": job_name}],
                }
            )

        # kube-state-metrics
        scrape_jobs.append(
            {
                **base_job,
                "job_name": "kube-state-metrics",
                "metrics_path": "/api/v1/namespaces/kube-system/services/kube-state-metrics:http-metrics/proxy/metrics",  # noqa
                "relabel_configs": [{"target_label": "job", "replacement": "kube-state-metrics"}],
                "static_configs": [{"targets": ["localhost:16443"]}],
            }
        )

    # kube-proxy
    scrape_jobs.append(
        {
            **base_job,
            "job_name": "kube-proxy",
            "static_configs": [{"targets": ["localhost:10250"]}],
            "relabel_configs": [{"target_label": "job", "replacement": "kube-proxy"}],
        }
    )

    # kubelet
    for job_name, metrics_path in (
        ("kubelet", "/metrics"),
        ("kubelet-cadvisor", "/metrics/cadvisor"),
        ("kubelet-probes", "/metrics/probes"),
    ):
        scrape_jobs.append(
            {
                **base_job,
                "job_name": job_name,
                "metrics_path": metrics_path,
                "static_configs": [{"targets": ["localhost:10250"], "labels": {"node": hostname}}],
                "relabel_configs": [
                    {"target_label": "metrics_path", "replacement": metrics_path},
                    {"target_label": "job", "replacement": "kubelet"},
                ],
            }
        )

    return scrape_jobs
