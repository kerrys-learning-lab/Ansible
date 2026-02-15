#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: kubeconfig_transform
short_description: Transform a kubeconfig file with YAML-aware replacements
description:
  - Reads a source kubeconfig YAML file, replaces the server loopback address
    with a provided FQDN, renames cluster and context entries from C(default)
    to a meaningful name, and writes the result to a destination file.
  - Uses ruamel.yaml for round-trip YAML handling to preserve formatting.
  - Idempotent -- only writes when the destination content would change.
options:
  src:
    description: Path to the source kubeconfig file.
    type: path
    required: true
  dest:
    description: Path to write the transformed kubeconfig.
    type: path
    required: true
  server:
    description:
      - FQDN or address to replace the loopback address in cluster server URLs.
      - Only the hostname portion of the URL is replaced; scheme and port are preserved.
    type: str
    required: true
  name:
    description:
      - Name to replace C(default) in cluster names, context names, and current-context.
    type: str
    required: true
  owner:
    description: Owner of the destination file.
    type: str
  group:
    description: Group of the destination file.
    type: str
  mode:
    description: File mode of the destination file.
    type: raw
author:
  - "Kerry's Learning Lab"
'''

EXAMPLES = r'''
- name: Transform kubeconfig for sharing
  kubeconfig_transform:
    src: /etc/kubeconfig
    dest: /usr/local/share/kubeconfig.d/kubeconfig.myhost.yaml
    server: myhost.example.com
    name: myhost
    owner: root
    group: root
    mode: "a=rX"
'''

RETURN = r'''
msg:
  description: Summary of actions performed.
  returned: always
  type: str
changed_fields:
  description: List of fields that were modified.
  returned: always
  type: list
  elements: str
'''

import os
import tempfile

from ansible.module_utils.basic import AnsibleModule

try:
    from ruamel.yaml import YAML
    HAS_RUAMEL = True
except ImportError:
    HAS_RUAMEL = False

try:
    from urllib.parse import urlparse, urlunparse
except ImportError:
    from urlparse import urlparse, urlunparse


def _replace_server_host(url, new_host):
    """Replace the hostname in a server URL, preserving scheme and port."""
    parsed = urlparse(url)
    # netloc may be host:port -- preserve the port
    if parsed.port:
        new_netloc = "{}:{}".format(new_host, parsed.port)
    else:
        new_netloc = new_host
    return urlunparse((parsed.scheme, new_netloc, parsed.path,
                       parsed.params, parsed.query, parsed.fragment))


def transform_kubeconfig(data, server, name):
    """Apply transformations to a parsed kubeconfig dict (ruamel CommentedMap).

    Returns a list of human-readable descriptions of changes made.
    """
    changes = []

    # 1. Replace server host in all clusters
    for cluster_entry in data.get("clusters", []):
        cluster = cluster_entry.get("cluster", {})
        old_url = cluster.get("server", "")
        if old_url:
            new_url = _replace_server_host(old_url, server)
            if new_url != old_url:
                cluster["server"] = new_url
                changes.append("cluster server: {} -> {}".format(old_url, new_url))

        # 2. Rename cluster name
        if cluster_entry.get("name") == "default":
            cluster_entry["name"] = name
            changes.append("cluster name: default -> {}".format(name))

    # 3. Rename user entries
    for user_entry in data.get("users", []):
        if user_entry.get("name") == "default":
            user_entry["name"] = name
            changes.append("user name: default -> {}".format(name))

    # 4. Update contexts
    for ctx_entry in data.get("contexts", []):
        ctx = ctx_entry.get("context", {})
        if ctx.get("cluster") == "default":
            ctx["cluster"] = name
            changes.append("context.cluster ref: default -> {}".format(name))

        if ctx.get("user") == "default":
            ctx["user"] = name
            changes.append("context.user ref: default -> {}".format(name))

        if ctx_entry.get("name") == "default":
            ctx_entry["name"] = name
            changes.append("context name: default -> {}".format(name))

    # 5. Update current-context
    if data.get("current-context") == "default":
        data["current-context"] = name
        changes.append("current-context: default -> {}".format(name))

    return changes


def main():
    module_args = {
        "src": {"type": "path", "required": True},
        "dest": {"type": "path", "required": True},
        "server": {"type": "str", "required": True},
        "name": {"type": "str", "required": True},
        "owner": {"type": "str", "required": False},
        "group": {"type": "str", "required": False},
        "mode": {"type": "raw", "required": False},
    }

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    if not HAS_RUAMEL:
        module.fail_json(msg="The ruamel.yaml Python package is required. "
                             "Install it with: pip install ruamel.yaml")

    src = module.params["src"]
    dest = module.params["dest"]
    server = module.params["server"]
    name = module.params["name"]

    if not os.path.isfile(src):
        module.fail_json(msg="Source file '{}' does not exist".format(src))

    yaml = YAML()
    yaml.preserve_quotes = True

    with open(src, "r") as f:
        data = yaml.load(f)

    if data is None:
        module.fail_json(msg="Source file '{}' is empty or not valid YAML".format(src))

    changes = transform_kubeconfig(data, server, name)

    # Render the transformed YAML to a string for comparison
    from io import StringIO
    buf = StringIO()
    yaml.dump(data, buf)
    new_content = buf.getvalue()

    # Check if dest already has the desired content
    changed = True
    if os.path.isfile(dest):
        with open(dest, "r") as f:
            existing = f.read()
        if existing == new_content:
            changed = False

    if changed and not module.check_mode:
        # Write atomically via temp file in the same directory
        dest_dir = os.path.dirname(dest) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dest_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(new_content)
            module.atomic_move(tmp_path, dest)
        except Exception:
            os.unlink(tmp_path)
            raise

    # Handle file attributes (owner, group, mode)
    file_args = module.load_file_common_arguments(module.params, path=dest)
    changed = module.set_fs_attributes_if_different(file_args, changed)

    msg = "; ".join(changes) if changes else "No transformations needed"
    module.exit_json(changed=changed, msg=msg, changed_fields=changes)


if __name__ == "__main__":
    main()
