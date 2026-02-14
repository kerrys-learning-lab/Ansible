#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: microk8s
short_description: Manage microk8s addons and repositories
description:
  - Enable or disable microk8s addons.
  - Add or remove microk8s addon repositories.
options:
  addons:
    description:
      - Dictionary containing addon configuration.
    type: dict
    suboptions:
      name:
        description: List of addon names.
        type: list
        elements: str
        required: true
      enable:
        description: Whether to enable or disable the addons.
        type: bool
        default: true
  repo:
    description:
      - Dictionary containing repository configuration.
    type: dict
    suboptions:
      name:
        description: Name of the repository.
        type: str
        required: true
      url:
        description: URL of the repository.
        type: str
      present:
        description: Whether the repository should be present or absent.
        type: bool
        default: true
  microk8s_path:
    description:
      - Path to the microk8s executable.
    type: path
    default: /snap/bin/microk8s
author:
  - "Kerry's Learning Lab"
'''

EXAMPLES = r'''
- name: Enable dns and storage addons
  microk8s:
    addons:
      name:
        - dns
        - storage
      enable: true

- name: Add a custom repository
  microk8s:
    repo:
      name: my-repo
      url: https://github.com/my-repo/addons
      present: true
'''

RETURN = r'''
msg:
  description: Status message regarding the actions performed.
  returned: always
  type: str
'''

from ansible.module_utils.basic import AnsibleModule
import yaml


class Microk8s:
    def __init__(self, module):
        self.module = module
        self.path = module.params['microk8s_path']
        self._module_status = None
        self._repo_status = None

    @property
    def module_status(self):
        if self._module_status is None:
            self._module_status = self._execute(["status"], structured=True)
            if 'addons' in self._module_status:
                self._module_status = _list_to_map(self._module_status["addons"], "name")
            else:
                self.module.fail_json(msg="Could not parse microk8s status output: 'addons' key missing.")
        return self._module_status

    @property
    def repo_status(self):
        if self._repo_status is None:
            self._repo_status = self._execute(
                ["addons", "repo", "list"], structured=True, key="name"
            )
        return self._repo_status

    def enable_module(self, module):
        return self._apply_module_change("enabled", module)

    def disable_module(self, module):
        return self._apply_module_change("disabled", module)

    def add_repo(self, repo_name, repo_url):
        return self._apply_repo_change(True, repo_name, repo_url=repo_url)

    def remove_repo(self, repo_name):
        return self._apply_repo_change(False, repo_name)

    def _apply_repo_change(self, expected_present, repo_name, repo_url=None):
        result = {
            "changed": False,
        }

        command = ["addons", "repo"]
        command.append("add" if expected_present else "remove")
        command.append(repo_name)
        if repo_url is not None:
            command.append(repo_url)

        existing_repo = self.repo_status.get(repo_name)
        if (existing_repo is None and expected_present) or (
            existing_repo and not expected_present
        ):
            if not self.module.check_mode:
                self._execute(command)
            result["changed"] = True
            result[
                "msg"
            ] = "Repository '{}' {}".format(repo_name, 'added' if expected_present else 'removed')

        return result

    def _apply_module_change(self, desired_status, module):
        result = {
            "changed": False,
        }

        if self.module_status[module]["status"] != desired_status:
            self._execute([desired_status[:-1], module])
            result = _merge_results(
                result,
                {"changed": True, "msg": "Module '{}' {}".format(module, desired_status)},
            )

        return result

    def _execute(self, args, structured=False, key=None):
        command = [self.path] + args
        if structured:
            command.extend(["--format", "yaml"])

        rc, out, err = self.module.run_command(command, check_rc=True)

        if structured:
            result = yaml.safe_load(out)

            if key:
                result = _list_to_map(result, key)

        return result


def _merge_results(result, results):
    results = results if isinstance(results, list) else [results]
    for riter in results:
        result["changed"] |= riter["changed"]
        if "msg" in riter:
            if "msg" not in result:
                result["msg"] = riter["msg"]
            else:
                result["msg"] = "{}\n{}".format(result['msg'], riter['msg'])
    return result


def _list_to_map(values, key):
    if not values:
        return {}
    return {v[key]: v for v in values}


def main():
    module_args = {
        "addons": {
            "type": "dict",
            "required": False,
            "options": {
                "name": {"type": "list", "required": True, "elements": "str"},
                "enable": {"type": "bool", "required": False, "default": True},
            },
        },
        "repo": {
            "type": "dict",
            "required": False,
            "options": {
                "name": {"type": "str", "required": True},
                "url": {"type": "str"},
                "present": {"type": "bool", "required": False, "default": True},
            },
        },
        "microk8s_path": {
            "type": "path",
            "required": False,
            "default": "/snap/bin/microk8s",
        },
    }

    result = {"changed": False}

    ansible_module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_one_of=[("addons", "repo")],
    )

    microk8s = Microk8s(ansible_module)

    repo_spec = ansible_module.params.get("repo")
    if repo_spec:
        if repo_spec.get("present"):
            intermediate_result = microk8s.add_repo(repo_spec["name"], repo_spec["url"])
        else:
            intermediate_result = microk8s.remove_repo(repo_spec["name"])
        result = _merge_results(result, intermediate_result)

    addon_spec = ansible_module.params.get("addons")
    if addon_spec:
        enable = addon_spec["enable"]
        method = microk8s.enable_module if enable else microk8s.disable_module

        for module in addon_spec["name"]:
            intermediate_result = method(module)
            result = _merge_results(result, intermediate_result)

    ansible_module.exit_json(**result)


if __name__ == "__main__":
    main()
