#
# Copyright 2023 Canonical, Ltd.
#

import os
import shutil
from pathlib import Path
from urllib.request import urlopen

LIBRARIES = [
    ("grafana-agent", "cos_agent"),
]

DIR = "lib"

shutil.rmtree(DIR, ignore_errors=True)
os.mkdir(DIR)

for charm_name, library_name in LIBRARIES:
    url = f"https://charmhub.io/{charm_name}/libraries/{library_name}/download"
    path = f"lib/charms/{charm_name.replace('-', '_')}/v0/{library_name}.py"

    Path(path).parent.mkdir(parents=True, exist_ok=True)

    contents = urlopen(url).read().decode().strip()
    contents = contents.replace("\nPYDEPS =", "\n# PYDEPS =")

    Path(path).write_text(contents)
