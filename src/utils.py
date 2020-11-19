import subprocess


def join_url_from_add_node_output(output):
    """Extract the first join URL from the output of `microk8s add-node`."""
    lines = output.split('\n')
    lines = [line.strip() for line in lines]
    lines = [line for line in lines if line.startswith('microk8s join ')]
    return lines[0].split()[2]


def microk8s_ready():
    """Check if microk8s is ready.

    Since `microk8s status` always exits 0, we do this by parsing its output.

    """
    output = subprocess.check_output(['/snap/bin/microk8s', 'status']).decode('utf-8')
    return output.startswith('microk8s is running')
