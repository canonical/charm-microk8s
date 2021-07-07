import pytest
import os
import sh


class TestScale(object):
    """
    This test sets up a sizable cluster using juju.

    The juju controller should have been already bootstrapped.
    After the test ends the cluster is _not_ removed. The will have to inspect the cluster
    and juju remove the mk8s-scale application.


    The following environment variables can be set to configure the cluster setup:

    MK8S_CLUSTER_SIZE: the size of the cluster, defaults to 30
    NODE_CORES: the cores a node should have, defaults to 2
    NODE_MEM: the memory in GB a node should have, defaults to 4
    MK8S_CHARM: the MicroK8s charm to be used, defaults to cs:~pjdc/microk8s
    """

    @pytest.mark.skip(reason="Skip the scale test unless explicetely called")
    def test_scale(self):
        size = os.environ.get("MK8S_CLUSTER_SIZE", "30")
        cores = os.environ.get("NODE_CORES", "2")
        mem = os.environ.get("NODE_MEM", "4")
        charm = os.environ.get("MK8S_CHARM", "cs:~pjdc/microk8s")

        node_contrainets = "cores={} mem={}G".format(cores, mem)
        sh.juju("deploy", "-n", size, "--constraints", node_contrainets, charm, "mk8s-scale")
        sh.juju("wait")
        sh.juju("config", "mk8s-scale", "addons", "dns ingress prometheus")
