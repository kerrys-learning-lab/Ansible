# Ansible Infrastructure Configuration

This repository contains Ansible playbooks and roles for managing a homelab infrastructure including Kubernetes clusters, development workstations, and cluster services.

## Table of Contents

- [Architecture & Design Principles](#architecture--design-principles)
  - [Variable Merge Pattern](#variable-merge-pattern)
  - [Secrets Pattern](#secrets-pattern)
  - [Global Variables](#global-variables)
  - [The Lookup Pattern](#the-lookup-pattern)
  - [Role Structure](#role-structure)
  - [Complex Loop Decomposition](#complex-loop-decomposition)
  - [Self-Contained Roles](#self-contained-roles)
  - [Inventory Organization](#inventory-organization)
  - [Conditional Role and Task Execution](#conditional-role-and-task-execution)
  - [Network Topology Variables](#network-topology-variables)
  - [Helm Chart Conventions](#helm-chart-conventions)
  - [Kubernetes Resource Patterns](#kubernetes-resource-patterns)
  - [K8s Engine Abstraction](#k8s-engine-abstraction)
  - [K8s Role Scope: Infrastructure vs Extensions](#k8s-role-scope-infrastructure-vs-extensions)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Running Ansible](#running-ansible)
- [Operational Notes](#operational-notes)
  - [ArgoCD Cluster Management](#argocd-cluster-management)
  - [GitLab Upgrades](#gitlab-upgrades)
  - [Proxmox Storage Setup](#proxmox-storage-setup)

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

### Secrets Pattern

Sensitive values (passwords, API keys, tokens) are stored separately from
role configuration and are **not** part of the Variable Merge Pattern.

#### Central Vault

All secrets originate from a single dictionary, `secrets_vault`, defined in
`group_vars/all/secrets.yaml`. This file may be encrypted with Ansible Vault
or stored as plain text (see [GETTING-STARTED.md](GETTING-STARTED.md)).

#### Role-Specific Secrets

Roles that need secrets define a separate `<role>_secrets` variable alongside
the main `<host>_<role>` variable. These are **not** merged into `<role>_vars`
-- they exist as standalone variables accessed directly in tasks.

```yaml
# File: host_vars/gitlab01/gitlab.yaml

# This IS part of the merge pattern (merged into gitlab_vars):
gitlab01_gitlab:
  application:
    crd_values:
      # ... configuration ...

# This is NOT merged -- it's a standalone variable used directly in tasks:
gitlab_secrets:
  backups:
    minio:
      key: "{{ lookup('ansible.builtin.vars', 'secrets_vault').gitlab.backups.minio.key }}"
  registry:
    postgresql:
      username: "{{ lookup('ansible.builtin.vars', 'secrets_vault').gitlab.registry.postgresql.username }}"
      password: "{{ lookup('ansible.builtin.vars', 'secrets_vault').gitlab.registry.postgresql.password }}"
```

**Why separate?** Keeping secrets out of the merge pipeline prevents them from
appearing in merged variable dumps and makes the sensitive/non-sensitive
boundary explicit.

**Usage in tasks:**
```yaml
# Configuration comes from merged vars:
access_key = {{ gitlab_vars.backups.minio.access }}
# Secrets come from the standalone variable:
secret_key = {{ gitlab_secrets.backups.minio.key }}
```

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
  inherited:
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
    dest: "{{ <role>_vars.inherited.downloads }}/artifact.tar.gz"
    owner: "{{ <role>_vars.inherited.owner }}"
    group: "{{ <role>_vars.inherited.group }}"
    mode: "{{ <role>_vars.inherited.mode }}"
```

### The Lookup Pattern

Variables defined in `group_vars/all/` (like `lan`, `secrets_vault`, and
`inherited`/`global`) are accessed using `lookup('ansible.builtin.vars', 'varname')`
rather than direct references:

```yaml
# Correct -- uses lookup:
domain: "{{ lookup('ansible.builtin.vars', 'lan').domain }}"
password: "{{ lookup('ansible.builtin.vars', 'secrets_vault').smb.password }}"
owner: "{{ lookup('ansible.builtin.vars', 'global').owner | default('root') }}"

# Incorrect -- direct reference:
domain: "{{ lan.domain }}"
```

**Why?** The lookup forces late binding, resolving the value when the variable
is actually used rather than when the file is loaded. This avoids circular
dependency issues that arise when `group_vars` and `host_vars` files reference
each other during Ansible's variable loading phase.

**When to use which:**
- **Lookup**: For cross-file references to `lan`, `secrets_vault`, `global`,
  or any variable defined outside the current file's scope (typically in
  `defaults/main.yaml` and `group_vars`/`host_vars` files).
- **Direct reference**: For variables within the same merged context, like
  `<role>_vars.inherited.kubeconfig` inside a task after the merge has
  already run.

### Role Structure

- **Organization:** Split complex logic into separate files included by `main.yaml`
- **Tags:**
  - Every task inherits the role's name as a tag (applied in playbook)
  - Sub-tasks can have granular tags (e.g., `install`, `config`)
- **Idempotency:** Tasks must check state before changing it, especially for `command`/`shell` modules

### Complex Loop Decomposition

When a task loop is complex — involving multiple steps per item, conditional
logic, or inline templates — extract the per-item work into a dedicated task
file and use `include_tasks` in the outer loop.  This keeps both files focused
and readable.

**Anti-pattern: everything in one file**

```yaml
# tasks/users-and-groups.yaml (hard to follow when each item needs many steps)
- name: Set env vars for each user
  ansible.builtin.lineinfile:
    path: "/home/{{ item.0.key }}/.bashrc"
    line: "export {{ item.1.key }}={{ item.1.value }}"
  loop: "{{ common_vars.users_and_groups.users | dict2items
            | selectattr('value.env', 'defined')
            | subelements('value.env') }}"
  # ... more tasks duplicated per user ...
```

**Preferred pattern: outer loop + inner task file**

```yaml
# tasks/users-and-groups.yaml -- drives the loop
- name: Configure environment variables for each user
  ansible.builtin.include_tasks: user-env-vars.yaml
  loop: "{{ common_vars.users_and_groups.users | dict2items
            | selectattr('value.env', 'defined') | list }}"
  loop_control:
    loop_var: user_item
    label: "{{ user_item.key }}"
```

```yaml
# tasks/user-env-vars.yaml -- focuses on a single user
- name: Ensure ~/.bashrc exports are present
  ansible.builtin.lineinfile:
    path: "/home/{{ user_item.key }}/.bashrc"
    line: "export {{ env_var.key }}={{ env_var.value }}"
  loop: "{{ user_item.value.env | dict2items }}"
  loop_control:
    loop_var: env_var
    label: "{{ env_var.key }}"
```

**Key details:**

- Use `loop_var` in the outer `loop_control` to give the item a meaningful
  name (e.g., `user_item`) so the inner file can reference it without
  shadowing the `item` variable.
- Use `import_tasks` for static includes (evaluated at parse time, tags
  propagate); use `include_tasks` when the filename or loop is dynamic
  (evaluated at run time).  Outer loops **must** use `include_tasks`.

**Real-world example:** `roles/common/tasks/users-and-groups.yaml` drives the
user loop and calls `include_tasks: user-env-vars.yaml` for the environment
variable work.

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

#### Host Type Groups

Groups can also express host-level characteristics that affect connection or
behavior. For example, the `proxmox` group captures Proxmox VE hosts which
require root SSH and no `become`/sudo:

```yaml
proxmox:
  hosts:
    elitedesk:
```

### Conditional Role and Task Execution

The playbook and roles use several patterns to conditionally include roles and
tasks. Understanding these is important when adding new hosts or roles.

#### Group Membership (Playbook Level)

Roles applied within a multi-role play use `group_names` to check whether the
current host belongs to a group:

```yaml
# In westsidestreet.net.yaml -- the k8s play applies to all k8s hosts,
# but GitLab and Runner roles only run on hosts in those specific groups:
- role: gitlab
  when: "'gitlab' in group_names"
- role: gitlab-runner
  when: "'gitlab_runner' in group_names"
```

**To enable a role for a host**, add the host to the appropriate inventory
group -- no playbook changes needed.

#### Variable Existence (Optional Roles)

Some roles only run when their configuration variable is defined:

```yaml
- role: argocd-server
  when: argocd_server is defined
```

**To enable ArgoCD on a host**, define `argocd_server` in that host's
`host_vars`. To disable it, remove the variable.

#### Feature Flags (Task Level)

The `k8s_engine.needs` dictionary controls which ecosystem components are
installed:

```yaml
# In roles/k8s-ecosystem/tasks/main.yaml:
- name: Configure k8s CSI Driver for SMB
  ansible.builtin.include_tasks: csi-driver-smb.yaml
  when: k8s_engine.needs.smb_driver | default(true)

- name: Configure k8s MetalLB
  ansible.builtin.include_tasks: metal-lb.yaml
  when: k8s_engine.needs.metallb | default(true)
```

These flags are set in the engine's group_vars (e.g.,
`group_vars/k8s_engine_k3s/main.yaml`).

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

### Helm Chart Conventions

All Helm-based installations follow a consistent variable and task structure.

#### Variable Structure

Helm charts are configured with a standard set of keys in role defaults:

```yaml
# roles/<role>/defaults/main.yaml
<role>_defaults:
  helm:
    name: release-name           # Helm release name
    namespace: target-namespace  # Kubernetes namespace
    chart:
      url: https://charts.example.io  # Chart repository URL (for HTTP repos)
      ref: chart-name                  # Chart name within the repo
      version: 1.2.3                   # Chart version
    # For OCI registries, use `oci` instead of `url`:
    # chart:
    #   oci: oci://registry.example.io/charts/chart-name
    #   version: 1.2.3

  # Helm values passed to the chart:
  helm_values: {}
```

#### Task Pattern

```yaml
- name: Install/Configure <Component> Using Helm
  kubernetes.core.helm:
    name: "{{ <role>_vars.helm.name }}"
    namespace: "{{ <role>_vars.helm.namespace }}"
    chart_repo_url: "{{ <role>_vars.helm.chart.url }}"
    chart_version: "{{ <role>_vars.helm.chart.version }}"
    chart_ref: "{{ <role>_vars.helm.chart.ref }}"
    release_values: "{{ <role>_vars.helm_values }}"
    create_namespace: true
    kubeconfig: "{{ <role>_vars.inherited.kubeconfig }}"
    wait: true
```

#### Helm Values from Templates

When Helm values require conditional logic (e.g., GitLab Runner's optional S3
cache), a Jinja2 template renders the values first:

```yaml
- name: Render Helm Configuration
  ansible.builtin.set_fact:
    rendered_values: "{{ lookup('ansible.builtin.template', 'values.j2.yaml') }}"

- name: Install via Helm
  kubernetes.core.helm:
    release_values: "{{ rendered_values | from_yaml }}"
    # ... other fields ...
```

Templates live in `roles/<role>/templates/` and access the merged `<role>_vars`
directly.

### Kubernetes Resource Patterns

Kubernetes resources are created inline using `kubernetes.core.k8s` with
`apply: true` for idempotency. Collections of resources (secrets, volumes,
certificates) use `dict2items` loops over dictionary variables:

```yaml
- name: Create K8s Certificate(s)
  kubernetes.core.k8s:
    state: present
    apply: true
    definition:
      apiVersion: cert-manager.io/v1
      kind: Certificate
      metadata:
        name: "{{ item.key }}"
        namespace: "{{ item.value.namespace }}"
      spec:
        secretName: "{{ item.key }}-tls"
        dnsNames: "{{ item.value.dnsNames }}"
        issuerRef:
          name: "{{ k8s_ecosystem_vars.cluster_cert_issuer.name }}"
          kind: ClusterIssuer
    kubeconfig: "{{ k8s_ecosystem_vars.inherited.kubeconfig }}"
  loop: "{{ k8s_ecosystem_vars.certificates | default({}) | dict2items }}"
  loop_control:
    label: "{{ item.key }}"
```

This pattern means adding a new certificate (or secret, volume, etc.) only
requires adding an entry to the appropriate dictionary in `host_vars` -- no
task changes needed.

### K8s Engine Abstraction

The `k8s-engine` role supports multiple Kubernetes distributions (K3S, RKE2,
CRC) through a conditional task loading pattern. This is **not** the Variable
Merge Pattern -- it uses a separate control variable.

#### Engine Selection

Each engine group defines a `k8s_engine` variable that selects the
distribution and declares feature requirements:

```yaml
# group_vars/k8s_engine_k3s/main.yaml
k8s_engine:
  engine: k3s
  needs:
    certmanager: true
    smb: true
    metallb: true
```

#### Conditional Task Loading

The role's `main.yaml` dispatches to engine-specific task files:

```yaml
- name: Install K3S
  ansible.builtin.import_tasks: k3s.yaml
  when: k8s_engine.engine == 'k3s'

- name: Install RKE2
  ansible.builtin.import_tasks: rke2.yaml
  when: k8s_engine.engine == 'rke2'
```

The `k8s_engine.needs` flags are consumed by the `k8s-ecosystem` role to
conditionally install components (see
[Conditional Role and Task Execution](#conditional-role-and-task-execution)).

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

#### User Creation

User must have password-less SSH to the target machine and must be able to
execute 'sudo' without requiring a password.

#### Ansible Galaxy Collections

How to update all collections:

```bash
for collection in $(ansible-galaxy collection list --format=json | jq -r '.["/usr/lib/python3/dist-packages/ansible_collections"] | keys[]'); do
  echo "Updating collection: ${collection}"
  ansible-galaxy collection install ${collection} --upgrade
done
```

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

#### NVIDIA Container Toolkit Configuration (nvidia-ctk)

After the toolkit is installed, the `nvidia` role can configure it for GPU
access in Kubernetes and/or Podman via the `ctk.runtimes` list.

| Runtime | What it does | Use case |
|---------|-------------|----------|
| `containerd` | Runs `nvidia-ctk runtime configure --runtime=containerd` and restarts the K8s engine service | GPU workloads in K3s/Kubernetes pods |
| `cdi` | Enables the `nvidia-cdi-refresh` systemd service to auto-generate CDI specs at `/var/run/cdi/nvidia.yaml` | GPU access in ad-hoc Podman containers |

The two modes are **not mutually exclusive** -- a host can enable both. They
operate at different layers (containerd config vs. CDI device spec) and don't
conflict as long as you don't try to use the GPU from both runtimes
simultaneously.

**Configuration** uses the standard Variable Merge Pattern. Enable runtimes in
the host's `_nvidia` variable:

```yaml
# host_vars/<host>/nvidia.yaml
<host>_nvidia:
  ctk:
    runtimes:
      - containerd
      - cdi
```

**Current host configuration:**

| Host | Runtimes | Rationale |
|------|----------|-----------|
| nvidia-5080 | `containerd` | Dedicated K3s GPU server |
| asus | `containerd`, `cdi` | Dev machine -- GPU in K3s and Podman |

#### GPU Support in Kubernetes (k8s-applications)

Hosts with `gpu.enabled: true` in their `_k8s_applications` variables get
three components deployed to the cluster:

1. **Node Feature Discovery (NFD)** — DaemonSet that detects hardware
   (PCI devices, CPU features, etc.) and labels nodes accordingly.

2. **NodeFeatureRule for NVIDIA** — A custom NFD rule that sets the label
   `nvidia.com/gpu.present=true` when PCI vendor `10de` (NVIDIA) is detected.
   This is necessary because NFD labels PCI devices with their class prefix
   (e.g., `pci-0300_10de.present`), but the NVIDIA device plugin's default
   node affinity expects `nvidia.com/gpu.present=true`. The NodeFeatureRule
   bridges this gap by deriving the expected label from NFD's raw detection.

3. **NVIDIA Device Plugin** — DaemonSet that exposes `nvidia.com/gpu`
   resources to the kubelet, allowing pods to request GPU access via
   `resources.limits`.

#### CNPG (CloudNativePG) in Kubernetes (k8s-applications)

Hosts with `cnpg.enabled: true` in their `_k8s_applications` variables get
three things deployed:

1. **`cnpg-local` StorageClass** — A dedicated `kubernetes.io/no-provisioner`
   class with `WaitForFirstConsumer` binding, separate from the generic `local`
   class so CNPG storage is clearly identified and independently configurable.

2. **CNPG Operator** — Deployed via Helm from `cloudnative-pg.github.io/charts`.
   Watches for `Cluster` CRs and manages the full PostgreSQL lifecycle
   (provisioning, failover, backups, upgrades).

3. **PersistentVolumes** — One PV per entry in `cnpg.local_volumes`, created
   under `/var/lib/k8s-local-volumes/cnpg/` and labelled `owner: <key>` for
   deterministic binding by CNPG `Cluster` CRs.

##### Adding a new CNPG database volume

Add an entry to `cnpg.local_volumes` in the host's `_k8s_applications` variable:

```yaml
# host_vars/<host>/k8s-applications.yaml
<host>_k8s_applications:
  cnpg:
    enabled: true
    local_volumes:
      cnpg--<my-namespace>--<my-app>: # PV name — must be unique cluster-wide
        capacity: 20Gi
        path: cnpg/<my-namespace>/<my-app>    # relative to /var/lib/k8s-local-volumes/
        owner: 26               # postgres UID in CNPG images
        group: 26
        mode: u=rwx,go=
```

Then reference it from the ArgoCD `Cluster` CR via `matchLabels`:

```yaml
spec:
  instances: 1
  storage:
    size: 20Gi
    pvcTemplate:
      spec:
        storageClassName: cnpg-local   # matches cnpg.storage_class default
        selector:
          matchLabels:
            owner: cnpg--my-app-db
```

The CNPG operator creates a PVC per instance; Kubernetes binds it to the
matching PV via the label selector (same mechanism as Gitaly). For multi-instance
clusters, provision one PV per replica (e.g. `cnpg--my-app-db-1`,
`cnpg--my-app-db-2`) and use a dynamic provisioner instead of `matchLabels`.

The StorageClass name defaults to `cnpg-local` and can be overridden via
`cnpg.storage_class` in the host's `_k8s_applications` variable.

> **Note:** The postgres user UID in CNPG images is `26`. Verify with:
> ```bash
> kubectl run -it --rm cnpg-check \
>   --image=ghcr.io/cloudnative-pg/postgresql:16 \
>   --restart=Never -- id postgres
> ```

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

### Verifying GPU Access

After running the `nvidia` role with `ctk` configured, verify GPU access
is working on the target host.

#### Podman (CDI)

```bash
podman run --rm --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi
```

You should see your GPU listed with driver version and memory info.

#### K3s (containerd)

Apply a test pod:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test
spec:
  runtimeClassName: nvidia
  restartPolicy: Never
  containers:
    - name: gpu-test
      image: nvidia/cuda:12.6.0-base-ubuntu24.04
      command: ["nvidia-smi"]
      resources:
        limits:
          nvidia.com/gpu: "1"
```

```bash
kubectl apply -f gpu-test.yaml
kubectl logs gpu-test
kubectl delete pod gpu-test
```

> **Note:** Workload pods need both `runtimeClassName: nvidia` and a GPU
> resource limit. The `runtimeClassName` tells containerd to use the NVIDIA
> runtime, which injects the driver libraries and tools (e.g., `nvidia-smi`)
> into the container. The resource limit reserves a GPU device via the
> NVIDIA device plugin. Without the runtime class, the GPU device is
> allocated but the NVIDIA userspace tools and libraries are not available.
>
> The `nvidia.com/gpu` resource limit also requires the
> [NVIDIA device plugin](https://github.com/NVIDIA/k8s-device-plugin) DaemonSet
> to be deployed in the cluster. Without it, the kubelet won't advertise GPU
> resources and the pod will stay `Pending` with an `Insufficient nvidia.com/gpu`
> event.

### k8s-share Role: Delegation Caveat

In the `k8s-share` role, all tasks **except** `slurp` must be delegated to the
Ansible control node (`localhost`). The `slurp` task reads files from the remote
host (e.g., fetching a kubeconfig), but subsequent operations (writing files,
running kubectl) should execute locally. Forgetting to delegate causes tasks to
run on the remote host where the expected local paths and tools may not exist.

### Proxmox Storage Setup

After Ansible provisions disk partitions and LVM volume groups on a Proxmox host
(via the `common` role's `disk-management.yaml`), register the VGs as Proxmox
LVM-thin storage backends:

```bash
# Register storage backends in Proxmox
pvesm add lvmthin local-sda --vgname vg_sda --thinpool data --content images,rootdir
pvesm add lvmthin local-sdb --vgname vg_sdb --thinpool data --content images,rootdir
```

The new storage pools will then appear in the Proxmox UI when creating VMs.

See [disk-management-plan.md](disk-management-plan.md) for the full design and
variable schema.

---

## TODO

- Cert Manager
  - Installed via Helm Applications
  - Create an Issuer
  - Create k8s certificates
