import json
import os
import subprocess


def get_departing_unit_name():
    return os.environ.get('JUJU_DEPARTING_UNIT')


def join_url_from_add_node_output(output):
    """Extract the first join URL from the output of `microk8s add-node`."""
    lines = output.split('\n')
    lines = [line.strip() for line in lines]
    lines = [line for line in lines if line.startswith('microk8s join ')]
    return lines[0].split()[2]


class KubectlFailedError(Exception):
    pass


class MicroK8sNode:
    def __init__(self, result):
        self._result = result

    def exists(self):
        if self._result.returncode == 0:
            return True
        if 'NotFound' in self._result.stderr:
            return False
        raise KubectlFailedError('kubectl failed with no error output, rc={}'.format(self._result.returncode))

    def ready(self):
        if not self.exists():
            return False
        parsed = json.loads(self._result.stdout)
        conditions = parsed.get('status', {}).get('conditions', [])
        ready_conditions = [
            condition for condition in conditions
            if condition.get('type') == 'Ready' and condition.get('reason') == 'KubeletReady'
        ]
        if len(ready_conditions) != 1:
            return
        return ready_conditions[0].get('status') == 'True'


def get_microk8s_node(node_name):
    return MicroK8sNode(
        subprocess.run(
            ['/snap/bin/microk8s', 'kubectl', 'get', 'node', node_name, '-o', 'json'],
            capture_output=True,
            encoding='utf-8',
        )
    )


def get_microk8s_nodes_json():
    return subprocess.check_output(
        ['/snap/bin/microk8s', 'kubectl', 'get', 'nodes', '-o', 'json'],
        encoding='utf-8',
    )


def join_url_key(unit):
    return unit.name + '.join_url'


def close_port(port):
    subprocess.check_call(['close-port', port])


def open_port(port):
    subprocess.check_call(['open-port', port])


def microk8s_ready():
    """Check if microk8s is ready.

    Since `microk8s status` usually exits 0, we do this by parsing its output.
    """
    result = subprocess.run(
        ['/snap/bin/microk8s', 'status'],
        capture_output=True,
        encoding='utf-8',
    )
    if result.returncode > 0:
        return False
    return result.stdout.startswith('microk8s is running')
