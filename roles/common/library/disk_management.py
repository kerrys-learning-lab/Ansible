#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: disk_management
short_description: Declarative disk partitioning, LVM, filesystem, and mount management
description:
  - Manages the full lifecycle of block storage in a single declarative call.
  - Partitions physical disks (via pyparted), creates LVM volume groups, thin pools,
    logical volumes, filesystems, and mounts.
  - Idempotent -- checks current state before every operation.
options:
  disks:
    description:
      - Dictionary of physical disks to partition.
      - Keys are device paths (e.g. /dev/sda).
      - Values contain label (default gpt), force (default false), and partitions list.
    type: dict
    default: {}
  volume_groups:
    description:
      - Dictionary of LVM volume groups to create.
      - Keys are VG names (e.g. vg_sda).
      - Values contain pvs (list), optional thinpool (str), and optional logical_volumes (dict).
    type: dict
    default: {}
author:
  - "Kerry's Learning Lab"
'''

EXAMPLES = r'''
- name: Partition disk and create VG with thin pool
  disk_management:
    disks:
      /dev/sda:
        label: gpt
        force: true
        partitions:
          - number: 1
            size: "100%"
            flags: [lvm]
    volume_groups:
      vg_sda:
        pvs: [/dev/sda1]
        thinpool: data

- name: Full pipeline -- partition, VG, LV, filesystem, mount
  disk_management:
    disks:
      /dev/sdb:
        label: gpt
        force: true
        partitions:
          - number: 1
            size: "100%"
            flags: [lvm]
    volume_groups:
      gitlab:
        pvs: [/dev/sdb1]
        logical_volumes:
          data:
            size: 100%FREE
            filesystem: ext4
            mount: /var/lib/k8s-local-volumes
'''

RETURN = r'''
msg:
  description: Summary of actions performed.
  returned: always
  type: str
actions:
  description: List of individual actions taken, each with category and message.
  returned: always
  type: list
  elements: dict
reboot_required:
  description: Whether a reboot is needed (partition table changes).
  returned: always
  type: bool
'''

import os

from ansible.module_utils.basic import AnsibleModule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_bytes(n):
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024.0:
            return "{:.1f}{}".format(n, unit)
        n /= 1024.0
    return "{:.1f}PiB".format(n)


# ---------------------------------------------------------------------------
# Change tracking
# ---------------------------------------------------------------------------

class ChangeLog:
    """Accumulates change records and computes the overall changed flag."""

    def __init__(self):
        self.entries = []
        self._changed = False
        self._reboot_required = False

    @property
    def changed(self):
        return self._changed

    @property
    def reboot_required(self):
        return self._reboot_required

    def record(self, category, message, reboot_required=False):
        self.entries.append({"category": category, "message": message})
        self._changed = True
        if reboot_required:
            self._reboot_required = True

    def to_result(self):
        return {
            "changed": self._changed,
            "actions": self.entries,
            "msg": ("; ".join(e["message"] for e in self.entries)
                    if self.entries else "No changes needed"),
            "reboot_required": self._reboot_required,
        }

    def fail_context(self):
        """Return result dict without 'msg', for use with fail_json."""
        result = self.to_result()
        result.pop("msg", None)
        return result


# ---------------------------------------------------------------------------
# Main manager class
# ---------------------------------------------------------------------------

class DiskManager:

    def __init__(self, module):
        self.module = module
        self.changelog = ChangeLog()
        self._vg_cache = None
        self._mount_cache = None

    # ------------------------------------------------------------------
    # Public orchestration
    # ------------------------------------------------------------------

    def ensure_disks(self, disks_spec):
        """Partition physical disks according to spec."""
        import parted as _parted  # noqa: F811 -- deferred import
        self._parted = _parted

        for device_path, disk_spec in disks_spec.items():
            label = disk_spec.get("label", "gpt")
            force = disk_spec.get("force", False)
            partitions = disk_spec.get("partitions", [])

            current = self._get_disk_state(device_path)
            table_changed = self._ensure_partition_table(
                device_path, label, force, current,
            )

            if table_changed:
                current = self._get_disk_state(device_path)

            for part_spec in partitions:
                self._ensure_partition(device_path, part_spec, current)

    def ensure_volume_groups(self, vg_spec):
        """Create VGs, thin pools, LVs, filesystems, and mounts."""
        for vg_name, vg_config in vg_spec.items():
            pvs = vg_config.get("pvs", [])
            self._ensure_vg(vg_name, pvs)

            thinpool_name = vg_config.get("thinpool")
            if thinpool_name:
                self._ensure_thinpool(vg_name, thinpool_name)

            for lv_name, lv_config in vg_config.get("logical_volumes", {}).items():
                lv_extended = self._ensure_lv(vg_name, lv_name, lv_config)

                device = "/dev/{}/{}".format(vg_name, lv_name)
                fstype = lv_config.get("filesystem")
                if fstype:
                    self._ensure_filesystem(device, fstype,
                                            resize=lv_extended)

                mount_path = lv_config.get("mount")
                if mount_path and fstype:
                    owner = lv_config.get("owner", "root")
                    group = lv_config.get("group", "root")
                    mode = lv_config.get("mode", "0755")
                    self._ensure_mount_dir(mount_path, owner, group, mode)
                    self._ensure_mount(device, mount_path, fstype)

    # ------------------------------------------------------------------
    # Disk / partition helpers  (pyparted)
    # ------------------------------------------------------------------

    def _get_disk_state(self, device_path):
        parted = self._parted
        try:
            device = parted.getDevice(device_path)
        except parted.DeviceException:
            self.module.fail_json(
                msg="Device '{}' not found or not accessible".format(device_path),
                **self.changelog.fail_context(),
            )

        try:
            disk = parted.newDisk(device)
        except parted.DiskException:
            return {"has_table": False, "label": None, "partitions": []}

        parts = []
        for p in disk.partitions:
            flags = []
            if p.getFlag(parted.PARTITION_LVM):
                flags.append("lvm")
            if p.getFlag(parted.PARTITION_BOOT):
                flags.append("boot")
            if p.getFlag(parted.PARTITION_RAID):
                flags.append("raid")
            parts.append({
                "number": p.number,
                "flags": flags,
            })

        return {
            "has_table": True,
            "label": disk.type,
            "partitions": parts,
        }

    def _ensure_partition_table(self, device_path, label, force, current):
        parted = self._parted

        # Idempotent: correct table already exists -- nothing to do
        if current["has_table"] and current["label"] == label:
            return False

        # Wrong label: require force to overwrite
        if current["has_table"] and not force:
            self.module.fail_json(
                msg="Device '{}' has '{}' partition table but '{}' was "
                    "requested. Set force=true to overwrite.".format(
                        device_path, current["label"], label),
                **self.changelog.fail_context(),
            )

        if self.module.check_mode:
            self.changelog.record(
                "partition_table",
                "Would create {} table on {}".format(label, device_path),
                reboot_required=True,
            )
            return True

        device = parted.getDevice(device_path)
        disk = parted.freshDisk(device, label)
        disk.commit()

        self.changelog.record(
            "partition_table",
            "Created {} partition table on {}".format(label, device_path),
            reboot_required=True,
        )
        return True

    def _ensure_partition(self, device_path, part_spec, current):
        parted = self._parted

        part_number = part_spec["number"]
        desired_flags = part_spec.get("flags", [])

        existing = None
        for p in current.get("partitions", []):
            if p["number"] == part_number:
                existing = p
                break

        if existing is not None:
            if set(existing["flags"]) == set(desired_flags):
                return False
            self.module.warn(
                "Partition {} on {} exists but flags differ "
                "(have={}, want={}). Skipping flag change for safety.".format(
                    part_number, device_path, existing["flags"], desired_flags,
                )
            )
            return False

        size_spec = part_spec.get("size", "100%")
        if size_spec != "100%":
            self.module.fail_json(
                msg="Unsupported partition size '{}'. Only '100%' is currently supported.".format(
                    size_spec),
                **self.changelog.fail_context(),
            )

        if self.module.check_mode:
            self.changelog.record(
                "partition",
                "Would create partition {} on {}".format(part_number, device_path),
                reboot_required=True,
            )
            return True

        device = parted.getDevice(device_path)
        disk = parted.newDisk(device)

        free_regions = disk.getFreeSpaceRegions()
        if not free_regions:
            self.module.fail_json(
                msg="No free space on {} for partition {}".format(
                    device_path, part_number),
                **self.changelog.fail_context(),
            )

        region = max(free_regions, key=lambda r: r.length)
        constraint = device.optimalAlignedConstraint
        geometry = parted.Geometry(
            device=device, start=region.start, length=region.length,
        )

        new_partition = parted.Partition(
            disk=disk,
            type=parted.PARTITION_NORMAL,
            geometry=geometry,
        )

        flag_map = {
            "lvm": parted.PARTITION_LVM,
            "boot": parted.PARTITION_BOOT,
            "raid": parted.PARTITION_RAID,
        }
        for flag_name in desired_flags:
            flag_const = flag_map.get(flag_name)
            if flag_const is None:
                self.module.fail_json(
                    msg="Unknown partition flag: '{}'".format(flag_name),
                    **self.changelog.to_result(),
                )
            new_partition.setFlag(flag_const)

        disk.addPartition(partition=new_partition, constraint=constraint)
        disk.commit()

        self.changelog.record(
            "partition",
            "Created partition {} on {} with flags {}".format(
                part_number, device_path, desired_flags),
            reboot_required=True,
        )
        return True

    # ------------------------------------------------------------------
    # LVM helpers  (subprocess via module.run_command)
    # ------------------------------------------------------------------

    def _run_cmd(self, cmd, check_rc=True):
        rc, stdout, stderr = self.module.run_command(cmd)
        if check_rc and rc != 0:
            self.module.fail_json(
                msg="Command failed: {}\nrc={}\nstdout={}\nstderr={}".format(
                    " ".join(cmd), rc, stdout, stderr),
                **self.changelog.fail_context(),
            )
        return rc, stdout, stderr

    def _get_vg_state(self):
        if self._vg_cache is not None:
            return self._vg_cache

        rc, stdout, _ = self._run_cmd(
            ["vgs", "--noheadings", "--nosuffix", "--separator", "|",
             "-o", "vg_name,pv_name"],
            check_rc=False,
        )

        result = {}
        if rc == 0 and stdout.strip():
            for line in stdout.strip().splitlines():
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 2:
                    vg_name, pv_name = parts[0], parts[1]
                    if vg_name not in result:
                        result[vg_name] = {"pvs": []}
                    if pv_name and pv_name not in result[vg_name]["pvs"]:
                        result[vg_name]["pvs"].append(pv_name)

        self._vg_cache = result
        return result

    def _get_lv_state(self, vg_name):
        rc, stdout, _ = self._run_cmd(
            ["lvs", "--noheadings", "--nosuffix", "--units", "b",
             "--separator", "|",
             "-o", "lv_name,lv_size,lv_attr,pool_lv", vg_name],
            check_rc=False,
        )

        result = {}
        if rc == 0 and stdout.strip():
            for line in stdout.strip().splitlines():
                parts = [p.strip() for p in line.split("|")]
                if parts:
                    size_str = parts[1] if len(parts) > 1 else None
                    size_bytes = None
                    if size_str:
                        try:
                            size_bytes = int(float(size_str))
                        except (ValueError, TypeError):
                            pass
                    result[parts[0]] = {
                        "size": size_str,
                        "size_bytes": size_bytes,
                        "attr": parts[2] if len(parts) > 2 else None,
                        "pool": parts[3] if len(parts) > 3 else None,
                    }
        return result

    def _get_vg_free_bytes(self, vg_name):
        """Returns the free space in a VG in bytes."""
        rc, stdout, _ = self._run_cmd(
            ["vgs", "--noheadings", "--nosuffix", "--units", "b",
             "-o", "vg_free", vg_name],
            check_rc=False,
        )
        if rc == 0 and stdout.strip():
            try:
                return int(float(stdout.strip()))
            except (ValueError, TypeError):
                pass
        return 0

    def _ensure_vg(self, vg_name, pvs):
        vg_state = self._get_vg_state()

        if vg_name in vg_state:
            existing_pvs = set(vg_state[vg_name]["pvs"])
            desired_pvs = set(pvs)
            if existing_pvs == desired_pvs:
                return False
            self.module.warn(
                "VG '{}' exists but PVs differ (have={}, want={}). "
                "Manual intervention required.".format(
                    vg_name, sorted(existing_pvs), sorted(desired_pvs)),
            )
            return False

        if self.module.check_mode:
            self.changelog.record(
                "vg", "Would create VG '{}' with PVs {}".format(vg_name, pvs))
            return True

        for pv in pvs:
            self._run_cmd(["pvcreate", "--force", pv])

        self._run_cmd(["vgcreate", vg_name] + pvs)
        self._vg_cache = None

        self.changelog.record(
            "vg", "Created VG '{}' with PVs {}".format(vg_name, pvs))
        return True

    def _ensure_thinpool(self, vg_name, pool_name):
        lv_state = self._get_lv_state(vg_name)

        if pool_name in lv_state:
            attr = lv_state[pool_name].get("attr", "")
            if attr and attr[0] == "t":
                return False
            self.module.fail_json(
                msg="LV '{}/{}' exists but is not a thin pool (attr='{}')".format(
                    vg_name, pool_name, attr),
                **self.changelog.fail_context(),
            )

        if self.module.check_mode:
            self.changelog.record(
                "thinpool",
                "Would create thin pool '{}/{}'".format(vg_name, pool_name),
            )
            return True

        self._run_cmd([
            "lvcreate", "-l", "100%FREE", "-T",
            "{}/{}".format(vg_name, pool_name),
        ])

        self.changelog.record(
            "thinpool",
            "Created thin pool '{}/{}'".format(vg_name, pool_name),
        )
        return True

    @staticmethod
    def _parse_size_to_bytes(size_str):
        """Parse a human size string (e.g. '10G', '500M') to bytes.

        Returns None for percentage-based sizes like '100%FREE'.
        """
        size_str = size_str.strip()
        if "%" in size_str:
            return None

        multipliers = {
            "B": 1,
            "K": 1024,
            "M": 1024 ** 2,
            "G": 1024 ** 3,
            "T": 1024 ** 4,
        }
        # Check if last char is a unit suffix
        if size_str[-1:].upper() in multipliers:
            unit = size_str[-1:].upper()
            number = size_str[:-1]
        else:
            # Assume bytes
            unit = "B"
            number = size_str

        try:
            return int(float(number) * multipliers[unit])
        except (ValueError, TypeError):
            return None

    def _ensure_lv(self, vg_name, lv_name, lv_config):
        lv_state = self._get_lv_state(vg_name)
        size = lv_config.get("size", "100%FREE")

        if lv_name in lv_state:
            return self._maybe_extend_lv(vg_name, lv_name, size, lv_state[lv_name])

        if self.module.check_mode:
            self.changelog.record(
                "lv",
                "Would create LV '{}/{}' size={}".format(vg_name, lv_name, size),
            )
            return True

        if "%" in size:
            size_flag = ["-l", size]
        else:
            size_flag = ["-L", size]

        self._run_cmd(["lvcreate"] + size_flag + ["-n", lv_name, vg_name])

        self.changelog.record(
            "lv",
            "Created LV '{}/{}' size={}".format(vg_name, lv_name, size),
        )
        return True

    def _maybe_extend_lv(self, vg_name, lv_name, desired_size, current_lv):
        """Extend an existing LV if the desired size is larger than current.

        Returns True if the LV was extended (signals that a filesystem resize
        is needed).
        """
        current_bytes = current_lv.get("size_bytes")
        if current_bytes is None:
            return False

        # Percentage-based sizes (e.g. 100%FREE): extend if there is free
        # space in the VG
        if "%" in desired_size:
            free_bytes = self._get_vg_free_bytes(vg_name)
            # Use a 4MiB threshold to avoid trivial extends from rounding
            if free_bytes < 4 * 1024 * 1024:
                return False

            if self.module.check_mode:
                self.changelog.record(
                    "lv_extend",
                    "Would extend LV '{}/{}' by {} using {}".format(
                        vg_name, lv_name, _fmt_bytes(free_bytes), desired_size),
                )
                return True

            self._run_cmd([
                "lvextend", "-l", "+{}".format(desired_size),
                "/dev/{}/{}".format(vg_name, lv_name),
            ])

            self.changelog.record(
                "lv_extend",
                "Extended LV '{}/{}' by {} using {}".format(
                    vg_name, lv_name, _fmt_bytes(free_bytes), desired_size),
            )
            return True

        # Absolute sizes (e.g. 10G)
        desired_bytes = self._parse_size_to_bytes(desired_size)
        if desired_bytes is None:
            return False

        # Only extend if desired is meaningfully larger (>= 4MiB difference)
        if desired_bytes - current_bytes < 4 * 1024 * 1024:
            return False

        if self.module.check_mode:
            self.changelog.record(
                "lv_extend",
                "Would extend LV '{}/{}' from {} to {}".format(
                    vg_name, lv_name,
                    _fmt_bytes(current_bytes), _fmt_bytes(desired_bytes)),
            )
            return True

        self._run_cmd([
            "lvextend", "-L", desired_size,
            "/dev/{}/{}".format(vg_name, lv_name),
        ])

        self.changelog.record(
            "lv_extend",
            "Extended LV '{}/{}' from {} to {}".format(
                vg_name, lv_name,
                _fmt_bytes(current_bytes), _fmt_bytes(desired_bytes)),
        )
        return True

    # ------------------------------------------------------------------
    # Filesystem helpers
    # ------------------------------------------------------------------

    def _get_fs_type(self, device):
        rc, stdout, _ = self._run_cmd(
            ["blkid", "-o", "value", "-s", "TYPE", device],
            check_rc=False,
        )
        if rc == 0 and stdout.strip():
            return stdout.strip()
        return None

    # Map of filesystem types to their resize commands.
    # Each value is a list: the command and its args, with '{}' as a
    # placeholder for the device path.
    _FS_RESIZE_CMDS = {
        "ext2": ["resize2fs", "{}"],
        "ext3": ["resize2fs", "{}"],
        "ext4": ["resize2fs", "{}"],
        "xfs": ["xfs_growfs", "{}"],
    }

    def _ensure_filesystem(self, device, fstype, resize=False):
        current_fs = self._get_fs_type(device)

        if current_fs == fstype:
            if resize:
                return self._resize_filesystem(device, fstype)
            return False

        if current_fs is not None and current_fs != fstype:
            self.module.fail_json(
                msg="Device '{}' has filesystem '{}' but '{}' was requested. "
                    "Refusing to overwrite.".format(device, current_fs, fstype),
                **self.changelog.fail_context(),
            )

        if self.module.check_mode:
            self.changelog.record(
                "filesystem",
                "Would create {} on {}".format(fstype, device),
            )
            return True

        self._run_cmd(["mkfs", "-t", fstype, device])

        self.changelog.record(
            "filesystem",
            "Created {} filesystem on {}".format(fstype, device),
        )
        return True

    def _resize_filesystem(self, device, fstype):
        """Grow a filesystem to fill its underlying device after an lvextend."""
        resize_template = self._FS_RESIZE_CMDS.get(fstype)
        if resize_template is None:
            self.module.warn(
                "Don't know how to resize filesystem type '{}' on {}. "
                "Manual resize required.".format(fstype, device),
            )
            return False

        cmd = [part.format(device) if "{}" in part else part
               for part in resize_template]

        if self.module.check_mode:
            self.changelog.record(
                "fs_resize",
                "Would resize {} filesystem on {}".format(fstype, device),
            )
            return True

        self._run_cmd(cmd)

        self.changelog.record(
            "fs_resize",
            "Resized {} filesystem on {}".format(fstype, device),
        )
        return True

    # ------------------------------------------------------------------
    # Mount helpers
    # ------------------------------------------------------------------

    def _get_mount_state(self):
        if self._mount_cache is not None:
            return self._mount_cache

        result = {}
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3:
                        result[parts[1]] = {"src": parts[0], "fstype": parts[2]}
        except IOError:
            self.module.warn("Could not read /proc/mounts")

        self._mount_cache = result
        return result

    def _ensure_mount_dir(self, path, owner, group, mode):
        import pwd
        import grp

        if os.path.isdir(path):
            return False

        if self.module.check_mode:
            self.changelog.record(
                "directory",
                "Would create directory {}".format(path),
            )
            return True

        os.makedirs(path, exist_ok=True)

        try:
            uid = pwd.getpwnam(owner).pw_uid
        except KeyError:
            uid = int(owner) if str(owner).isdigit() else 0
        try:
            gid = grp.getgrnam(group).gr_gid
        except KeyError:
            gid = int(group) if str(group).isdigit() else 0

        os.chown(path, uid, gid)
        os.chmod(path, int(str(mode), 8))

        self.changelog.record(
            "directory",
            "Created directory {} (owner={}, group={}, mode={})".format(
                path, owner, group, mode),
        )
        return True

    def _ensure_fstab_entry(self, device, path, fstype):
        fstab_path = "/etc/fstab"
        entry_line = "{}\t{}\t{}\tdefaults\t0\t0".format(device, path, fstype)

        try:
            with open(fstab_path, "r") as f:
                fstab_contents = f.read()
        except IOError:
            self.module.fail_json(
                msg="Cannot read {}".format(fstab_path),
                **self.changelog.fail_context(),
            )

        for line in fstab_contents.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            parts = stripped.split()
            if len(parts) >= 2 and parts[1] == path:
                return False

        if self.module.check_mode:
            self.changelog.record(
                "fstab",
                "Would add fstab entry for {} -> {}".format(device, path),
            )
            return True

        with open(fstab_path, "a") as f:
            f.write(entry_line + "\n")

        self.changelog.record(
            "fstab",
            "Added fstab entry: {}".format(entry_line),
        )
        return True

    def _ensure_mount(self, device, path, fstype):
        mount_state = self._get_mount_state()

        self._ensure_fstab_entry(device, path, fstype)

        if path in mount_state:
            return False

        if self.module.check_mode:
            self.changelog.record(
                "mount",
                "Would mount {} on {}".format(device, path),
            )
            return True

        self._run_cmd(["mount", "-t", fstype, device, path])
        self._mount_cache = None

        self.changelog.record(
            "mount",
            "Mounted {} on {} ({})".format(device, path, fstype),
        )
        return True


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------

def main():
    module_args = {
        "disks": {
            "type": "dict",
            "required": False,
            "default": {},
        },
        "volume_groups": {
            "type": "dict",
            "required": False,
            "default": {},
        },
    }

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    manager = DiskManager(module)

    disks_spec = module.params.get("disks") or {}
    if disks_spec:
        manager.ensure_disks(disks_spec)

    vg_spec = module.params.get("volume_groups") or {}
    if vg_spec:
        manager.ensure_volume_groups(vg_spec)

    module.exit_json(**manager.changelog.to_result())


if __name__ == "__main__":
    main()
