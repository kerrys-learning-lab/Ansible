#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: kubeconfig_merge
short_description: Merge multiple kubeconfig files into one
description:
  - Reads all kubeconfig YAML files matching a glob pattern from a source
    directory and merges their clusters, users, and contexts into a single
    kubeconfig file.
  - Uses ruamel.yaml for round-trip YAML handling to preserve formatting.
  - Idempotent -- only writes when the destination content would change.
options:
  src_dir:
    description: Directory containing individual kubeconfig files.
    type: path
    required: true
  dest:
    description: Path to write the merged kubeconfig.
    type: path
    required: true
  pattern:
    description: Glob pattern for matching kubeconfig files in C(src_dir).
    type: str
    default: "kubeconfig.*.yaml"
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
- name: Merge all kubeconfigs into a single file
  kubeconfig_merge:
    src_dir: /usr/local/share/kubeconfig.d
    dest: /etc/kubeconfig
    owner: root
    group: root
    mode: "a=rX"
'''

RETURN = r'''
msg:
  description: Summary of actions performed.
  returned: always
  type: str
files_merged:
  description: List of source files that were merged.
  returned: always
  type: list
  elements: str
'''

import glob
import os
import tempfile

from ansible.module_utils.basic import AnsibleModule

try:
    from ruamel.yaml import YAML
    HAS_RUAMEL = True
except ImportError:
    HAS_RUAMEL = False


def merge_kubeconfigs(files, yaml):
    """Read and merge multiple kubeconfig files into a single structure."""
    merged = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [],
        "contexts": [],
        "users": [],
        "current-context": None,
    }

    for filepath in sorted(files):
        with open(filepath, "r") as f:
            data = yaml.load(f)

        if data is None:
            continue

        for cluster in data.get("clusters", []):
            merged["clusters"].append(cluster)

        for context in data.get("contexts", []):
            merged["contexts"].append(context)

        for user in data.get("users", []):
            merged["users"].append(user)

        if merged["current-context"] is None and data.get("current-context"):
            merged["current-context"] = data["current-context"]

    return merged


def main():
    module_args = {
        "src_dir": {"type": "path", "required": True},
        "dest": {"type": "path", "required": True},
        "pattern": {"type": "str", "default": "kubeconfig.*.yaml"},
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

    src_dir = module.params["src_dir"]
    dest = module.params["dest"]
    pattern = module.params["pattern"]

    if not os.path.isdir(src_dir):
        module.fail_json(msg="Source directory '{}' does not exist".format(src_dir))

    files = glob.glob(os.path.join(src_dir, pattern))
    if not files:
        module.fail_json(msg="No files matching '{}' found in '{}'".format(pattern, src_dir))

    yaml = YAML()
    yaml.preserve_quotes = True

    merged = merge_kubeconfigs(files, yaml)

    # Render to string for comparison
    from io import StringIO
    buf = StringIO()
    yaml.dump(merged, buf)
    new_content = buf.getvalue()

    # Check if dest already has the desired content
    changed = True
    if os.path.isfile(dest) and not os.path.islink(dest):
        with open(dest, "r") as f:
            existing = f.read()
        if existing == new_content:
            changed = False

    if changed and not module.check_mode:
        # Remove symlink if present
        if os.path.islink(dest):
            os.unlink(dest)

        # Write atomically via temp file
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

    basenames = [os.path.basename(f) for f in sorted(files)]
    msg = "Merged {} kubeconfig(s): {}".format(len(files), ", ".join(basenames))
    module.exit_json(changed=changed, msg=msg, files_merged=basenames)


if __name__ == "__main__":
    main()
