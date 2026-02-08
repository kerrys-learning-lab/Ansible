# Ansible Infrastructure Configuration

This repository contains Ansible playbooks and roles for managing a homelab infrastructure including Kubernetes clusters, development workstations, and cluster services.

## Table of Contents

- [Architecture & Design Principles](#architecture--design-principles)
  - [Variable Merge Pattern](#variable-merge-pattern)
  - [Global Variables](#global-variables)
  - [Role Structure](#role-structure)
  - [Self-Contained Roles](#self-contained-roles)
  - [Inventory Organization](#inventory-organization)
  - [Network Topology Variables](#network-topology-variables)
  - [K8s Role Scope: Infrastructure vs Extensions](#k8s-role-scope-infrastructure-vs-extensions)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Running Ansible](#running-ansible)
- [Operational Notes](#operational-notes)
  - [ArgoCD Cluster Management](#argocd-cluster-management)
  - [GitLab Upgrades](#gitlab-upgrades)

---

## Architecture & Design Principles

### Variable Merge Pattern

The primary mechanism for configuration management is the **Variable Merge Pattern**, allowing hierarchical overrides and extensions of role configurations via group and host variables using `community.general.merge_variables`.

#### Role Defaults

- Defined in `roles/<role>/defaults/main.yaml`
- Variable name: `<role>_defaults`
- Contains baseline configuration (dictionaries, lists)

#### Overriding/Extending Variables

Groups and hosts override/extend role variables using naming conventions:

**Variable naming:** `<group-name>_<role>` or `<host-name>_<role>`
**File naming:** `group_vars/<role>.yaml` or `host_vars/<role>.yaml`

**Examples:**
```yaml
# File: host_vars/elitedesk/common.yaml
elitedesk_common:
  packages:
    - vim
    - htop

# File: group_vars/development/common.yaml
development_common:
  packages:
    - build-essential
```

#### Task Implementation

The first task in `roles/<role>/tasks/main.yaml` performs the merge:

```yaml
- name: Merge <role> Configuration
  ansible.builtin.set_fact:
    <role>_vars: |
      {{ lookup('community.general.merge_variables',
                '_<role>',
                pattern_type='suffix',
                initial_value=<role>_defaults,
                override='ignore') }}
```

For roles split across multiple task files, each sub-task file has a corresponding nested key in the role's variables (e.g., `common_vars.resolve` for `roles/common/tasks/resolve.yaml`).

### Global Variables

Global variables provide **centralized cross-role configuration** for common attributes like file ownership, permissions, and standard paths. This prevents duplication and ensures consistency across all roles.

#### Location

Global variables are defined in:
```
group_vars/all/global.yaml
```

#### Available Attributes

| Attribute | Default | Purpose |
|-----------|---------|---------|
| `owner` | `root` | Default file/directory owner |
| `group` | `root` | Default file/directory group |
| `mode` | `a=rX` | Default file/directory permissions |
| `working` | `/var/lib/ansible` | Root directory for ephemeral work products |
| `install` | `/usr/local/install` | Directory for installed software |
| `source` | `/usr/local/src` | Directory for source code |
| `secrets` | `/usr/local/secrets` | Directory for sensitive files |
| `kubeconfig` | `/etc/kubeconfig` | Path to shared Kubernetes config |

#### Working Directory Structure

The `working` directory organizes ephemeral Ansible artifacts:

- **`{{ global.working }}/downloads`** - Shared download cache for all roles
- **`{{ global.working }}/{{ role_name }}`** - Role-specific generated files (YAML, configs, etc.)
- **`{{ global.working }}/facts.d`** - Custom Ansible facts

#### How Roles Reference Global Variables

Roles access global variables using the **lookup pattern with fallback defaults**:

```yaml
# In roles/<role>/defaults/main.yaml
<role>_defaults:
  global:
    owner: "{{ lookup('ansible.builtin.vars', 'global').owner | default('root') }}"
    group: "{{ lookup('ansible.builtin.vars', 'global').group | default('root') }}"
    mode: "{{ lookup('ansible.builtin.vars', 'global').mode | default('a=rX') }}"
    downloads: "{{ lookup('ansible.builtin.vars', 'global').working | default('/var/lib/ansible') }}/downloads"
    working: "{{ lookup('ansible.builtin.vars', 'global').working | default('/var/lib/ansible') }}/{{ role_name }}"
    kubeconfig: "{{ lookup('ansible.builtin.vars', 'global').kubeconfig | default('/etc/kubeconfig') }}"
```

**Pattern benefits:**
- **Centralized changes**: Update `group_vars/all/global.yaml` to affect all roles
- **Fallback safety**: Roles work even if global variables aren't defined
- **Minimal duplication**: Only include global attributes the role actually uses

**Usage in tasks:**
```yaml
- name: Download artifact
  ansible.builtin.get_url:
    url: "{{ tool_url }}"
    dest: "{{ <role>_vars.global.downloads }}/artifact.tar.gz"
    owner: "{{ <role>_vars.global.owner }}"
    group: "{{ <role>_vars.global.group }}"
    mode: "{{ <role>_vars.global.mode }}"
```

### Role Structure

- **Organization:** Split complex logic into separate files included by `main.yaml`
- **Tags:**
  - Every task inherits the role's name as a tag (applied in playbook)
  - Sub-tasks can have granular tags (e.g., `install`, `config`)
- **Idempotency:** Tasks must check state before changing it, especially for `command`/`shell` modules

### Self-Contained Roles

Roles must manage their own dependencies without relying on other roles to install prerequisites.

**Implementation:**
- Include package installation tasks within the role
- Example: `c++-development` installs `build-essential`

**Benefit:**
- Allows running specific roles via `--tags` (e.g., `--tags c++`) without breaking
- Ansible's idempotency prevents redundant operations

**Exception:** Roles can assume basic bootstrapping from `common` role (system utilities like curl, network config, standard paths). Roles should only handle their specific domain dependencies.

### Inventory Organization

Use Ansible groups to express "what hosts are" rather than variables.

For components with multiple implementations (e.g., Kubernetes distributions), use nested groups:

```yaml
k8s:  # Parent group: all Kubernetes hosts
  children:
    rke2:  # Child group: RKE2 distribution
      hosts:
        elitedesk:
        nvidia-5080:
    crc:  # Child group: CodeReady Containers
      hosts:
        asus:
```

**Benefits:**
- Self-documenting inventory
- No validation/assertion logic needed in playbooks
- Clear separation in playbook structure
- Easy to add new implementations (e.g., `k3s`, `microk8s`)

### Network Topology Variables

Network topology information is centralized in the `lan` variable with the following structure:

- **`lan.ip`**: Key/value pairs mapping "short name" to IP address
  - Example: `lan.ip.gateway: "192.168.0.1"`
- **`lan.fqdn`**: Key/value pairs mapping "short name" to fully qualified domain name
  - Example: `lan.fqdn.elitedesk: "elitedesk.westsidestreet.net"`
- **`lan.endpoint`**: Key/value pairs mapping "short name" to host:port
  - Example: `lan.endpoint.nas: "nas.westsidestreet.net:445"`

**Usage in roles:**
```yaml
host: "{{ lookup('ansible.builtin.vars', 'lan').fqdn.nas }}"
```

### K8s Role Scope: Infrastructure vs Extensions

The `k8s` role focuses on **core Kubernetes infrastructure** - enabling standard K8s resources to function. Cluster **extensions** are separate roles.

**Belongs in `k8s` role:**
- Native K8s resources (namespaces, storage classes, secrets, certificates)
- Infrastructure components that enable core resources:
  - Helm CLI (required for CSI and cert-manager installation)
  - cert-manager (infrastructure for TLS/certificates)
  - CSI drivers (infrastructure for storage)

**Separate roles for extensions:**
- Sealed Secrets (encrypted secrets operator)
- Metal-LB (load balancer implementation)
- ArgoCD, GitLab, etc. (cluster applications)

**Rationale:**
- Conceptual clarity: `k8s` = "prepare cluster for standard K8s usage"
- Optional extensions: Not all clusters need all tools
- Follows existing pattern: Applications are separate roles
- Clean conditionals: Roles handle their own skip logic internally

---

## Getting Started

### Prerequisites

#### RKE2 Installation

[RKE2 Installation Quickstart](https://docs.rke2.io/install/quickstart)

```bash
curl -sfL https://get.rke2.io | sudo sh -
```

#### NVIDIA Container Toolkit

[Installing the NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
```

### Running Ansible

Variables are encrypted using Ansible Vault. A wrapper script (`ansible.sh`) incorporates the vault password automatically:

```bash
# Run all Ansible tasks against all hosts
ansible.sh

# Run all Ansible tasks against specific host
ansible.sh --limit asus

# Run specific role/tasks against specific host
ansible.sh --limit asus --tags common

# Dry run to see what would change
ansible.sh --check
```

**Manual execution (without wrapper):**
```bash
ansible-playbook \
  --vault-password-file ~/.ansible-vault-password \
  --inventory inventory \
  westsidestreet.net.yaml
```

**Gather facts from all hosts:**
```bash
ansible -i inventory/ all -m ansible.builtin.setup --tree /tmp/facts
```

---

## Operational Notes

### ArgoCD Cluster Management

#### Add a Cluster to ArgoCD

1. **Update kubeconfig for external access:**
   - Copy `/etc/kubeconfig` and replace the loopback address (127.0.0.1) with the machine's IP address or hostname

2. **Login to ArgoCD:**
   ```bash
   argocd login argocd.westsidestreet.net
   ```

3. **Add the cluster:**
   ```bash
   argocd --kubeconfig /var/lib/ansible/kubeconfig.d/<host> \
     cluster add --yes default \
     --name <cluster-name> \
     --server-name argocd.westsidestreet.net
   ```

### GitLab Upgrades

#### Current Versions

Last checked: 2026-01-27

| GitLab | Operator | Helm chart |
|--------|----------|------------|
| 18.8.2 | 2.8.2    | 9.8.2      |

Release notes: https://gitlab.com/gitlab-org/cloud-native/gitlab-operator/-/releases

#### Upgrading PostgreSQL Database

Run from a machine with cluster access (e.g., `elitedesk`):

```bash
curl -s "https://gitlab.com/gitlab-org/charts/gitlab/-/raw/${GITLAB_RELEASE}/scripts/database-upgrade" | \
  bash -s -- -n gitlab-system pre
```

---

## TODO

- Cert Manager
  - Installed via Helm Applications
  - Create an Issuer
  - Create k8s certificates
