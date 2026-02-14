#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: crc
short_description: Manage RedHat CodeReady Containers (CRC) configuration
description:
  - Configure CRC settings and run setup.
options:
  user:
    description: The system user to run CRC commands as.
    type: str
    required: true
  config:
    description: Dictionary of CRC configuration values.
    type: dict
    required: false
  setup:
    description: Run 'crc setup' if true.
    type: bool
    default: false
  start:
    description: Start the CRC instance if it is not running.
    type: bool
    default: false
  kubeconfig:
    description: Dictionary to configure kubeconfig export and permissions.
    type: dict
    suboptions:
      link:
        description: Path to link the kubeconfig file to.
        type: path
      mode:
        description: File mode (octal like "0644" or symbolic like "a=rX") for the source kubeconfig.
        type: str
  crc_path:
    description: Path to the crc executable.
    type: path
    default: /usr/local/bin/crc
'''

EXAMPLES = r'''
- name: Configure CRC
  crc:
    user: kerry
    config:
      consent-telemetry: "no"
      memory: 12000
    setup: true
    start: true
    kubeconfig:
      link: /var/lib/crc/kubeconfig
      mode: "0644"
'''

RETURN = r'''
msg:
  description: Summary of actions performed.
  returned: always
  type: str
'''

from ansible.module_utils.basic import AnsibleModule
import os
import pwd
import tempfile

class CRCManager:
    DEFAULTS = {
        'preset': {
            'value': 'openshift',
            'expected': "Default value 'openshift' is used",
        },
    }

    def __init__(self, module):
        self.module = module
        self.path = module.params['crc_path']
        self.user = module.params['user']

    def _execute(self, args):
        """
        Executes crc command as the target user using runuser.
        """
        # We use runuser to execute the command as the specific user
        # to ensure ~/.crc configuration is applied to the correct home dir.
        cmd = ['runuser', '-u', self.user, '--', self.path] + args

        rc, out, err = self.module.run_command(cmd)
        return rc, out.strip(), err

    def get_config_value(self, key):
        """
        Gets a single configuration value.
        Returns None if the key is unset or invalid.
        """
        rc, out, err = self._execute(['config', 'get', key])

        if rc != 0:
            # If the key doesn't exist or isn't set, CRC might return non-zero.
            # We treat this as None/Empty for comparison.
            return None

        default = CRCManager.DEFAULTS.get(key)
        if default and default['expected'] in out:
            return default['value']

        # CRC output for 'get' is typically just the value, but we strip whitespace
        return out

    def set_config_value(self, key, value):
        """
        Sets a configuration value.
        """
        if self.module.check_mode:
            return

        rc, out, err = self._execute(['config', 'set', key, str(value)])
        if rc != 0:
            self.module.fail_json(msg="Failed to set '{}': {}".format(key, err))

    def run_setup(self):
        """
        Runs crc setup.
        """
        if self.module.check_mode:
            return

        rc, out, err = self._execute(['setup'])
        if rc != 0:
            self.module.fail_json(msg="Failed to run crc setup: {}".format(err))

    def is_running(self):
        """
        Checks if CRC is running based on status return code.
        """
        rc, out, err = self._execute(['status'])
        return rc == 0 and 'Running' in out

    def start_instance(self):
        """
        Starts the CRC instance.
        """
        if self.module.check_mode:
            return

        rc, out, err = self._execute(['start'])
        if rc != 0:
            self.module.fail_json(msg="Failed to start crc: {}".format(err))

    def check_concurrent_user(self):
        """
        Checks if another user is running a CRC instance.
        Returns the username of the other user if found, else None.
        """
        # ps -eo user,args
        rc, out, err = self.module.run_command(['ps', '-eo', 'user,args'])
        if rc != 0:
            self.module.warn("Could not check for concurrent CRC instances: ps command failed")
            return None

        for line in out.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) != 2:
                continue

            proc_user, proc_args = parts

            # Filter for qemu processes related to CRC
            # CRC VMs typically run as qemu-system-x86_64 and have 'crc' in the path or name
            if 'qemu' in proc_args and 'crc' in proc_args:
                if proc_user != self.user:
                    return proc_user
        return None

    def export_kubeconfig(self, dest):
        try:
            user_entry = pwd.getpwnam(self.user)
            home = user_entry.pw_dir
        except KeyError:
            self.module.fail_json(msg="User '{}' not found".format(self.user))

        kubeconfig_src = os.path.join(home, '.kube', 'config')

        if not os.path.exists(kubeconfig_src):
            self.module.warn("Kubeconfig not found at '{}'. Cannot export.".format(kubeconfig_src))
            return False

        # Check if dest is already a symlink to src
        if os.path.islink(dest) and os.readlink(dest) == kubeconfig_src:
            return False

        if self.module.check_mode:
            return True

        # Remove existing file or link if it exists
        if os.path.lexists(dest):
            try:
                os.unlink(dest)
            except OSError as e:
                self.module.fail_json(msg="Failed to remove existing file '{}': {}".format(dest, e))

        try:
            os.symlink(kubeconfig_src, dest)
            return True
        except Exception as e:
            self.module.fail_json(msg="Failed to link kubeconfig to '{}': {}".format(dest, e))

    def ensure_kubeconfig_permissions(self, mode=0o644):
        """
        Ensures ~/.kube/config has specific permissions.
        """
        try:
            user_entry = pwd.getpwnam(self.user)
            home = user_entry.pw_dir
            kubeconfig_path = os.path.join(home, '.kube', 'config')

            if os.path.exists(kubeconfig_path):
                cmd = ['chmod', mode, kubeconfig_path]
                self.module.run_command(cmd)
        except Exception as e:
            self.module.warn("Failed to set permissions on kubeconfig: {}".format(e))
        return False

def main():
    module_args = {
        "user": {"type": "str", "required": True},
        "config": {"type": "dict", "required": False},
        "setup": {"type": "bool", "default": False},
        "start": {"type": "bool", "default": False},
        "kubeconfig": {
            "type": "dict",
            "required": False,
            "options": {
                "link": {"type": "path", "required": False},
                "mode": {"type": "str", "required": False},
            }
        },
        "crc_path": {"type": "path", "default": "/usr/local/bin/crc"},
    }

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    crc = CRCManager(module)
    result = {'changed': False, 'msg': []}

    # 1. Handle Configuration (Iterative Approach)
    if module.params['config']:
        for key, value in module.params['config'].items():
            # Normalize value to string for comparison
            # CRC booleans are usually "yes"/"no", but input might be True/False
            desired_val = str(value)
            if isinstance(value, bool):
                desired_val = "yes" if value else "no"

            current_val = crc.get_config_value(key)

            # Compare: If current is None (unset) or different, we update
            if current_val != desired_val:
                crc.set_config_value(key, desired_val)
                result['changed'] = True
                result['msg'].append("Set '{}' to '{}'".format(key, desired_val))

    # 2. Handle Setup
    # Note: 'crc setup' is generally safe to re-run, but it takes time.
    # Ideally, we only run it if config changed or if explicitly requested.
    if module.params['setup']:
        # Simple idempotency: If we changed config, we likely need setup.
        # Or we just run it if requested.
        crc.run_setup()
        result['changed'] = True
        result['msg'].append("Ran crc setup")

    # 3. Handle Start
    if module.params['start']:
        if not crc.is_running():
            conflict_user = crc.check_concurrent_user()
            if conflict_user:
                module.fail_json(msg="CRC is already running for user '{}'. Only one instance is allowed.".format(conflict_user))

            crc.start_instance()
            result['changed'] = True
            result['msg'].append("Started crc instance")

    # 4. Handle Kubeconfig
    kubeconfig_param = module.params.get('kubeconfig')
    if kubeconfig_param:
        mode_arg = kubeconfig_param.get('mode')
        if mode_arg:
            # normalize_mode handles both symbolic (a=rX) and octal (0644) formats
            mode = crc.normalize_mode(mode_arg, is_dir=False)
            if crc.ensure_kubeconfig_permissions(mode):
                result['changed'] = True
                result['msg'].append("Updated kubeconfig permissions to {}".format(mode_arg))

        link_arg = kubeconfig_param.get('link')
        if link_arg:
            if crc.export_kubeconfig(link_arg):
                result['changed'] = True
                result['msg'].append("Exported kubeconfig to {}".format(link_arg))

    module.exit_json(**result)

if __name__ == '__main__':
    main()
