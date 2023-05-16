#
# Copyright 2023 Canonical, Ltd.
#

from pathlib import Path

import graphviz

DIR = Path(__file__).absolute().parent


cp = graphviz.Digraph("microk8s control plane", filename=DIR / "control-plane", format="png")

cp.attr(rankdir="LR", size="20,30")

cp.attr("node", shape="none")
cp.node("text1", "MicroK8s Control Plane charm")
cp.node("", "juju deploy microk8s\nOR\njuju deploy microk8s --config role=control-plane")

cp.attr("node", shape="doublecircle")
cp.node("deploy", "deploy:\ninstalled=false")
cp.node("joined", "joined:\ninstalled=true\njoined=true\nleaving=false\nis_leader=false")
cp.node("leader", "leader:\ninstalled=true\njoined=true\nleaving=false\nis_leader=true")

cp.attr("node", shape="circle")
cp.node("installed", "installed:\ninstalled=true\njoined=false")
cp.node("leaving", "leaving:\ninstalled=true\njoined=true\nleaving=true")
cp.node("joining", "joining:\ninstalled=true\njoined=false\njoin_url=<from relation>")
cp.node("add-node")

cp.edge("", "deploy")

cp.edge("deploy", "deploy", label="failed to install")
cp.edge("deploy", "installed", label="snap install microk8s")

cp.edge("installed", "joining", label="peer_relation_joined\ngot join_url")
cp.edge("installed", "leader", label="leader\nnot available join_url\nbootstrap cluster")

cp.edge("joining", "installed", label="failed to join")
cp.edge("joining", "joined", label="microk8s join")

cp.edge("joined", "leaving", label="microk8s_relation_broken")
cp.edge("joined", "joined", label="config_changed")
cp.edge("joined", "leader", label="become leader")

cp.edge("leader", "joined", label="demoted")
cp.edge("leader", "leader", label="config_changed")
cp.edge("leader", "add-node", label="relation_joined")
cp.edge("leader", "remove-node", label="relation_departed")
cp.edge("leader", "leaving", label="microk8s_relation_broken")

cp.edge("leaving", "installed", label="microk8s leave")
cp.edge("leaving", "joined", label="failed to leave")

cp.edge("add-node", "leader", label="microk8s add-node\nset join_url in relation")

cp.edge("remove-node", "leader", label="microk8s remove-node")


cp.render(cleanup=True)


w = graphviz.Digraph("microk8s worker", filename=DIR / "worker", format="png")

w.attr(rankdir="LR", size="20,30")

w.attr("node", shape="none")
w.node("text1", "MicroK8s Worker charm")
w.node("", "juju deploy microk8s --config role=worker")

w.attr("node", shape="doublecircle")
w.node("deploy", "deploy:\ninstalled=false")
w.node("joined", "joined:\ninstalled=true\njoined=true\nleaving=false")

w.attr("node", shape="circle")
w.node("installed", "installed:\ninstalled=true\njoined=false")
w.node("leaving", "leaving:\ninstalled=true\njoined=true\nleaving=true")
w.node("joining", "joining:\ninstalled=true\njoined=false\njoin_url=<from relation>")

w.edge("", "deploy")

w.edge("deploy", "deploy", label="failed to install")
w.edge("deploy", "installed", label="snap install microk8s")

w.edge("installed", "joining", label="microk8s_relation_joined, got join_url")

w.edge("joining", "installed", label="failed to join")
w.edge("joining", "joined", label="microk8s join")

w.edge("joined", "leaving", label="microk8s_relation_broken")
w.edge("joined", "joined", label="config_changed")

w.edge("leaving", "installed", label="microk8s leave")
w.edge("leaving", "joined", label="failed to leave")

w.render(cleanup=True)


r = graphviz.Digraph("microk8s relations", filename=DIR / "relations", format="png")

r.attr(rankdir="LR", size="20,30")

r.attr("node", shape="none")
r.node("", "Charm relations\tjuju relate microk8s:microk8s-provides microk8s-worker:microk8s")

r.attr("node", shape="circle")
r.node("cp", "microk8s\n\nrole=control-plane")
r.node("w", "microk8s-worker\n\nrole=worker")

r.edge("cp", "cp", "peer (microk8s-peer)\nannounce hostnames of all peers)")
r.edge("cp", "w", "microk8s-provides (microk8s-info)\ncontrol-plane offer join_url to worker nodes")
r.edge("w", "cp", "microk8s (microk8s-info)\nworkers announce hostnames")

r.render(cleanup=True)
