#!/usr/bin/env python3

import os
import json

from tempfile import NamedTemporaryFile


def node_address_entries(nodes):
    entries = {}
    for node in nodes["items"]:
        hosts = []
        ips = []
        for address in node["status"]["addresses"]:
            if address["type"] == "Hostname":
                hosts.append(address["address"])
            if address["type"] == "InternalIP":
                ips.append(address["address"])
        for ip in sorted(ips):
            entries[ip] = sorted(hosts)
    return entries


def update_hosts_with(hosts, entries):
    lines = hosts.rstrip("\n").split("\n")
    newlines = []
    entry_hostnames = set()

    for hk, kv in entries.items():
        for h in kv:
            entry_hostnames.add(h)

    for line in lines:
        if line.startswith("#"):
            newlines.append(line)
            continue
        fields = line.split()
        if not fields:
            newlines.append(line)
            continue

        # Remove hostnames for which we have data from this line...
        replacement_hostnames = [host for host in fields[1:] if host not in entry_hostnames]
        # ...and emit the replacement only if at least one hostname remains.
        if not replacement_hostnames or replacement_hostnames[0].startswith("#"):
            continue
        if replacement_hostnames != fields[1:]:
            newlines.append(fields[0] + "\t" + " ".join(replacement_hostnames))
            continue
        newlines.append(line)

    for k in sorted(entries):
        newlines.append(k + "\t" + " ".join(entries[k]))

    return newlines


def sync_rename_sync(src, dst):
    """Rename src on top of dst, as safely as possible."""
    # Flush source file to disk.
    srcfd = os.open(src, 0, 0o644)
    os.fsync(srcfd)
    os.close(srcfd)
    # Replace destination file with source file.
    os.rename(src, dst)
    # Flush directory to disk.
    dirfd = os.open(os.path.dirname(dst), os.O_DIRECTORY, 0o755)
    os.fsync(dirfd)
    os.close(dirfd)


def read_etc_hosts():
    return open("/etc/hosts").read()


def write_temporary_file(filename, contents, encoding="utf-8"):
    """Write contents to a new file alongside filename, ready to be renamed into place."""
    directory = os.path.dirname(filename)
    prefix = ".{}-".format(os.path.basename(filename))
    with NamedTemporaryFile(prefix=prefix, dir=directory, delete=False) as ntf:
        ntf.write("\n".join(contents).encode(encoding) + b"\n")
        return ntf.name


def refresh_etc_hosts(nodes_json, expected_hosts):
    """Update /etc/hosts based on the output of `kubectl get nodes -o json`.

    Return a set naming the missing hosts, if any."""
    nodes = json.loads(nodes_json)
    entries = node_address_entries(nodes)
    hosts = read_etc_hosts()
    newhosts = update_hosts_with(hosts, entries)
    src = write_temporary_file("/etc/hosts", newhosts)
    os.chmod(src, 0o644)
    try:
        sync_rename_sync(src, "/etc/hosts")
    except Exception:
        os.unlink(src)
        raise
    entry_hostnames = set()
    for ev in entries.values():
        entry_hostnames.update(ev)
    return set(expected_hosts).difference(entry_hostnames)
