# Suspended Task: Refactor Ansible Playbook and Roles

## 1. Objective

Refactor the existing Ansible repository to improve maintainability,
scalability, and usability. The primary mechanism for configuration
management will be the **Variable Merge Pattern**, allowing hierarchical
overrides and extensions of role configurations via Group and Host variables.

**Success Criteria:**
- [ ] All roles utilize the standard Variable Merge Pattern.
- [ ] Roles are self-contained yet composable.
- [ ] Playbooks support granular execution via `--tags` and `--limit`.
- [ ] Documentation exists for the repository and complex roles.

## 2. Design Standards & Patterns

### 2.1 Variable Merge Pattern

To allow flexible configuration (e.g., adding packages in `group_vars/all` and
then adding more in `host_vars/specific_host`), we use
`community.general.merge_variables`.

#### 2.1.1 Role Defaults

- Defined in `roles/<role>/defaults/main.yaml`.
- Variable Name: `<role>_defaults`
- Content: The baseline configuration (dictionaries, lists).

#### 2.1.2 Overriding/Extending a Role's Variables

- Groups and hosts may override/extend role variables by following the
  variable naming convention: `<group-name>_<role>` or `<host-name>_<role>`
  (incorporated by community.general.merge_variables by suffix matching)

- Groups and hosts should follow the file naming convention
  `group_vars/<role>.yaml` or `host_vars/<role>.yaml` to make it easy to
  locate related variables

- Examples:
  - Extending variables for the `common` role:
    - File: `host_vars/dev-vm/common.yaml`
      Variable: `devvm_common`
    - File: `group_vars/development/common.yaml`
      Variable: `development_common`

#### 2.1.3 Task Implementation

- The first task in `roles/<role>/tasks/main.yaml` is usually the merge
  operation.

- If a role is split across multiple task file, each file containing
  sub-tasks is associated to a similarly named key nested within the
  role's vars.

  - Example: `roles/common` has a collection of sub-tasks in
    `roles/common/tasks/resolve.yaml`.  The variables for these sub-tasks
    are found in `common_vars.resolve`

- Target Variable: `<role>_vars` or `<role>_<sub-category>_vars`

  - Example:
    ```yaml
    - name: "Merge <role> Configuration"
      set_fact:
        <role>_vars: |
          {{ lookup('community.general.merge_variables',
                    '_<role>',
                    pattern_type='suffix',
                    initial_value=<role>_defaults,
                    override='ignore') }}
    ```

### 2.2 Role Structure

- Split complex logic into separate files included by `main.yaml`.
- **Tags:**
  - Every task in a role should inherit the role's name as a tag (applied in
    the playbook).
  - Specific sub-tasks can have granular tags (e.g., `install`, `config`).
- **Idempotency:** Ensure tasks check state before changing it (especially
  `command`/`shell` modules).
- **Derived Facts:**
  - Create new facts (`set_fact`) if:
    - They **combine** multiple existing facts, OR
    - They're **used in multiple places** (DRY principle)
  - Do not create facts that simply rename or transform a single existing fact that's only used once
  - All facts created in a role must be prefixed with the role name (e.g., `k8s_` for the k8s role)
  - **Examples - Valid derived facts:**
    ```yaml
    # Combines version + system + architecture (used in multiple places)
    k8s_helm_filename: "helm-{{ k8s_vars.helm.version }}-{{ ansible_system | lower }}-{{ ansible_local['arch']['container'] }}.tar.gz"

    # Combines install path + version (used in multiple places)
    k8s_helm_version_path: "{{ k8s_vars.inherited.paths.install }}/{{ k8s_vars.helm.version }}"
    ```
  - **Example - Invalid (simple renaming used once):**
    ```yaml
    # Don't do this - just use ansible_system | lower directly where needed
    k8s_helm_system: "{{ ansible_system | lower }}"
    ```

### 2.3 Self-Contained Roles

- Roles must manage their own dependencies. I.e, do not rely on `common` or
  other roles to install prerequisites.
- **Implementation:**
  - Include package installation tasks within the role (e.g., `c++-development`
    installs `build-essential`).
  - **Benefit:** Allows running specific roles via `--tags`
    (e.g., `--tags c++`) without breaking due to missing dependencies, while
    Ansible's idempotency prevents redundant operations.

### 2.4 Inventory Organization

- Use Ansible groups to express "what hosts are" rather than variables
- For components with multiple implementations (e.g., Kubernetes distributions),
  use nested groups:
  - Parent group: `k8s` (all Kubernetes hosts)
  - Child groups: `k8s-engine-rke2`, `crc` (specific distributions)
- **Benefits:**
  - Self-documenting inventory
  - No validation/assertion logic needed in playbooks
  - Clear separation in playbook structure
  - Easy to add new implementations (e.g., `k3s`, `microk8s`)

### 2.5 Network Topology Variables

Network topology information is defined in the `lan` variable. Within that variable, the following structure applies:

- **`lan.ip`**: Key/value pairs mapping "short name" to IP address
  - Example: `lan.ip.gateway: "192.168.0.1"`
- **`lan.fqdn`**: Key/value pairs mapping "short name" to fully qualified domain name
  - Example: `lan.fqdn.elitedesk: "elitedesk.westsidestreet.net"`
- **`lan.endpoint`**: Key/value pairs mapping "short name" to host:port
  - Example: `lan.endpoint.nas: "nas.westsidestreet.net:445"`

This centralized approach allows roles to reference network locations using lookups:
```yaml
host: "{{ lookup('ansible.builtin.vars', 'lan').fqdn.nas }}"
```

### 2.6 K8s Role Organization: Engine, Tools, Configuration

Kubernetes functionality is split across three roles to separate concerns:

**`k8s-engine` - Distribution Installation:**
- Installs the Kubernetes distribution (RKE2, CRC, K3s, etc.)
- Uses `include_role` to delegate to specific engine implementations
- Just installation, no configuration

**`k8s-tools` - Operational Tools:**
- CLI tools needed to operate and manage Kubernetes clusters
- Installed on all k8s hosts immediately after engine installation
- Tools:
  - **Helm CLI** - Required for deploying k8s infrastructure components
  - **k9s** - Terminal UI for cluster management and debugging
  - Future: kubectl, kubectx, kubens, stern, etc.

**`k8s` - Cluster Configuration:**
- Configures the Kubernetes cluster infrastructure
- Uses Helm (installed by k8s-tools) to deploy infrastructure components
- Native K8s resources (namespaces, storage classes, secrets, certificates)
- Infrastructure components that enable core resources:
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

## 3. Refactoring Roadmap

### Phase 1: Base System (Linux Hosts)
- [x] **common** (Refactored)
- [ ] **nvidia** (Drivers/GPU setup) (Deferred)

### Phase 2: Kubernetes Infrastructure (Cluster Nodes)
- [x] **k8s-engine-rke2** (The K8s Engine) (Refactored)
- [x] **k8s** (Cluster configuration, Storage Classes, CSI) (Refactored)
- [ ] **k8s-share** (Kubeconfig distribution)

### Phase 3: Development Environment (Dev Toolss)
- [x] **workstation** (Consolidated from separate dev roles; renamed from `development` to avoid collision with `development` group)

### Phase 4: Cluster Services (K8s Workloads)
- [ ] **helm-applications** (Generic Helm installer)
- [ ] **argocd-server**
- [ ] **gitlab** (The big one)
- [ ] **elasticsearch-operator**


## 4. Current Focus

**Recently Completed:**

4. **Renamed `development` role to `workstation`** ✓
   - Resolved naming collision: `development` group vs `development` role
   - `development` group: extends other roles (k8s, etc.) for development hosts
   - `workstation` role: provisions a machine as a developer workstation
   - Renamed: `development_defaults` → `workstation_defaults`, `development_vars` → `workstation_vars`
   - Merge suffix: `_development` → `_workstation`
   - Updated: `group_vars/development/main.yaml` → `group_vars/development/workstation.yaml` with `development_workstation` variable
   - Fixed: handler bug referencing undefined `podman_vars` → `workstation_vars.podman`

**Next Up:** `k8s-share` role refactoring

**Follow-up Tasks:**
- [x] Delete `os` role and related variable files (fully replaced by `common`)
  - Deleted: `roles/os/`
  - Deleted: `group_vars/all/os.yaml`
  - Deleted: `group_vars/dev/os.yaml`
  - Deleted: `group_vars/development/os.yaml`

- [x] Delete `resolve` role and duplicate variable files (fully replaced by `common`)
  - Deleted: `roles/resolve/`
  - Deleted: `group_vars/all/resolve.yaml` (duplicate of common_defaults.resolve)
  - Deleted: `host_vars/elitedesk/resolve.yaml` (already in elitedesk_common.resolve)
  - Deleted: `host_vars/nvidia-5080/resolve.yaml` (already in nvidia5080_common.resolve)
  - Fixed: Typo in `host_vars/nvidia-5080/common.yaml` (nvidi5080 → nvidia5080)

- [x] Delete leftover `group_vars/dev/` directory (group renamed to `development`)
  - Deleted entire directory: `group_vars/dev/`
  - All configs already exist in `group_vars/development/` with correct naming
  - Fixed: K8s role merge error caused by old `k8s:` variable naming

- [ ] **Migrate packages from deleted OS files to common role:**
  - **From group_vars/all:** `smbclient`, `pigz`
  - **From group_vars/dev:** `age`, `python3-tk`, `gitlab-ci-local`, python3 packages, `swig`, `bash-completions`
  - **From group_vars/development:** `age`, python3 packages, `swig`,
  - **Action needed:** Create appropriate `group_vars/*/common.yaml` files with `<group>_common.packages`

- [ ] **Migrate users/groups from deleted OS files to common role:**
  - **From group_vars/dev & development:** podman group, kerry user → podman group
  - **Action needed:** Add to `group_vars/dev/common.yaml` and `group_vars/development/common.yaml` using `<group>_common.users_and_groups`

- [ ] **Replace hard-coded domain names with `lan` variable references:**
  - **Find and replace:** Hard-coded `westsidestreet.net` domain names
  - **Find and replace:** Hard-coded LAN FQDNs (e.g., `elitedesk.westsidestreet.net`)
  - **Action needed:** Use `lan.domain`, `lan.fqdn.*`, `lan.ip.*`, and `lan.endpoint.*` lookups instead
  - **Locations to check:** Role defaults, host_vars, group_vars, templates
  - **Example:** `elitedesk.westsidestreet.net` → `{{ lookup('ansible.builtin.vars', 'lan').fqdn.elitedesk }}`

- [ ] **Standardize role defaults to use optional global references:**
  - **Pattern:** All roles should have a `global` section in `<role>_defaults`
  - **Implementation:** Reference `group_vars/all/global` with fallback defaults
  - **Example:**
    ```yaml
    <role>_defaults:
      inherited:
        owner: "{{ lookup('ansible.builtin.vars', 'global').owner | default('root') }}"
        group: "{{ lookup('ansible.builtin.vars', 'global').group | default('root') }}"
        mode: "{{ lookup('ansible.builtin.vars', 'global').mode | default('a=rX') }}"
        working: "{{ lookup('ansible.builtin.vars', 'global').working | default('/var/lib/ansible') }}"
        install: "{{ lookup('ansible.builtin.vars', 'global').install | default('/usr/local/src') }}"
    ```
  - **Roles to update:** All roles with owner/group/mode/paths configurations
  - **Benefit:** DRY principle with optional dependencies - roles remain self-contained

- [ ] **For each role's defaults, add a note that the values can be changed globally by updating `group_vars/all/globals.yaml`**

- [ ] **Claude**
  - [ ] After running `dev-tools` role, still had to invoke Claude installer for myself
  - [ ] (sudo) npm install -g mcp-server-kubernetes
  - [ ] claude mcp add kubernetes -- npx mcp-server-kubernetes

**Note on Self-Containment:**
Roles can assume basic bootstrapping from `common` role (system utilities like
curl, network config, standard paths). Roles should only handle their specific
domain dependencies.

## 5. Verification & Testing

Some of the variables are encrypted using Ansible Vault.  I've created a
wrapper script that incorporates the Ansible Vault password automatically:

```bash
# 1. Run all Ansible tasks against all hosts
ansible.sh

# 2. Run all Ansible tasks against the `asus` host only:
ansible.sh --limit asus

# 3. Run a subset of tasks against the `asus` host
ansible.sh --limit asus --tags <role_name>
```
