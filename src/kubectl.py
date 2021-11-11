import subprocess

KUBECTL = "/snap/bin/kubectl"


def _kubectl(*args):
    cmd = [KUBECTL]
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True)


def get(kind, name, namespace="default", output="json"):
    return _kubectl("get", kind, "-n", namespace, name, "-o", output)


def patch(kind, name, patch, namespace="default"):
    return _kubectl("patch", kind, "-n", namespace, name, "--patch", patch)
