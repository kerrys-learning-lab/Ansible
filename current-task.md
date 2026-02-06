# Current Task: Refactor Ansible Playbook and Roles

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

### 2.3 Self-Contained Roles

- Roles must manage their own dependencies. I.e, do not rely on `common` or
  other roles to install prerequisites.
- **Implementation:**
  - Include package installation tasks within the role (e.g., `c++-development`
    installs `build-essential`).
  - **Benefit:** Allows running specific roles via `--tags`
    (e.g., `--tags c++`) without breaking due to missing dependencies, while
    Ansible's idempotency prevents redundant operations.

## 3. Refactoring Roadmap

### Phase 1: Base System (Linux Hosts)
- [x] **common** (Refactored)
- [ ] **synology-backup**
- [ ] **nvidia** (Drivers/GPU setup)

### Phase 2: Kubernetes Infrastructure (Cluster Nodes)
- [ ] **rke2** (The K8s Engine)
- [ ] **k8s** (Cluster configuration, Storage Classes, CSI)
- [ ] **k8s-share** (Kubeconfig distribution)

### Phase 3: Development Environment (Workstations)
- [ ] Collapse the separate development roles where it makes sense
  - [ ] Discuss a `k8s-development` role which captures (for example)
    `argocd-cli`, `helm-cli`, etc
- [ ] **argocd-cli**
- [ ] **helm-cli**
- [ ] **k9s**
- [ ] **podman**
- [ ] **aws-development**
- [ ] **c++-development**
- [ ] **gitlabci-local**
- [ ] **open-gl**

### Phase 4: Cluster Services (K8s Workloads)
- [ ] **helm-applications** (Generic Helm installer)
- [ ] **argocd-server**
- [ ] **gitlab** (The big one)
- [ ] **dependabot-gitlab**
- [ ] **elasticsearch-operator**

## 4. Current Focus

**Active Role:** `common`
**Goal:** Refactor to use the **Variable Merge Pattern** and ensure the role
is **Self-Contained**.

**Target Environment:**
- Host: `asus`
- Command: `ansible.sh --limit asus --tags common`

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