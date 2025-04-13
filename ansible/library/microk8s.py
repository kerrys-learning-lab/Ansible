from ansible.module_utils.basic import AnsibleModule
import subprocess
import yaml


class Microk8s:
    def __init__(self, path) -> None:
        self.path = path
        self._module_status = None
        self._repo_status = None
        pass

    @property
    def module_status(self):
        if self._module_status is None:
            self._module_status = self._execute(["status"], structured=True)
            self._module_status = self._module_status["addons"]
            self._module_status = _list_to_map(self._module_status, "name")
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
            self._execute(command)
            result["changed"] = True
            result[
                "msg"
            ] = f"Repository '{repo_name}' {'added' if expected_present else 'removed'}"

        return result

    def _apply_module_change(self, desired_status, module):
        result = {
            "changed": False,
        }

        if self.module_status[module]["status"] != desired_status:
            self._execute([desired_status[:-1], module])
            result = _merge_results(
                result,
                {"changed": True, "msg": f"Module '{module}' {desired_status}"},
            )

        return result

    def _execute(self, args, structured=False, key=None):
        command = [self.path, *args]
        if structured:
            command.append("--format")
            command.append("yaml")

        result = subprocess.check_output(command)

        if structured:
            result = yaml.safe_load(result)

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
                result["msg"] = f"{result['msg']}\n{riter['msg']}"
    return result


def _list_to_map(values, key):
    return {v[key]: v for v in values}


def main():
    module_args = {
        "addons": {
            "type": "dict",
            "required": False,
            "options": {
                "name": {"type": "list", "required": True},
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

    microk8s = Microk8s(ansible_module.params["microk8s_path"])

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
