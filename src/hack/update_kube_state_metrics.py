#
# Copyright 2023 Canonical, Ltd.
#
import sys
from datetime import datetime
from urllib.request import urlopen

VERSION = "v2.9.2"
SOURCE = (
    f"https://raw.githubusercontent.com/kubernetes/kube-state-metrics/{VERSION}/examples/standard"
)

data = [f"# Automatically generated by {sys.argv}", f"# Timestamp: {datetime.utcnow().isoformat()}"]

for file in [
    "cluster-role-binding.yaml",
    "cluster-role.yaml",
    "deployment.yaml",
    "service-account.yaml",
    "service.yaml",
]:
    source = f"{SOURCE}/{file}"
    data += ["---", f"# Source: {source}", urlopen(source).read().decode().strip()]

with open("src/deploy/kube-state-metrics.yaml", "w") as fout:
    fout.write("\n".join(data))