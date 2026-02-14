# Future Improvements

This document tracks potential enhancements and planned improvements for the Ansible infrastructure.

## Automation

### Implement Renovate for Version Tracking
**Priority:** Medium
**Effort:** Medium

Replace manual version checking with Renovate bot for automated dependency updates.

**Context:**
- We currently manage tool versions manually across 12+ different tools (Helm, k9s, RKE2, etc.)
- Need automated version tracking and update notifications
- Using GitLab (not GitHub)

**Implementation:**
1. Create `.gitlab/renovate.json` configuration
2. Add renovate annotations to all version fields in `roles/*/defaults/main.yaml`
3. Configure Renovate bot in GitLab (self-hosted or Mend.io)
4. Set up merge request auto-creation for version updates

**Resources:**
- [Renovate GitLab Documentation](https://docs.renovatebot.com/modules/platform/gitlab/)
- Regex manager pattern for YAML files
- Example annotation: `# renovate: datasource=github-releases depName=helm/helm`

**Related Tasks:**
- See "Remove Dependabot artifacts" below

---

### Remove Dependabot Artifacts
**Priority:** Low
**Effort:** Low

Clean up partially-started but never-completed Dependabot configuration.

**Note:** This is a prerequisite cleanup before implementing Renovate above.

---

## Refactoring

### Standardize Global Variable References
**Priority:** High
**Effort:** Low
**Status:** In Progress

Ensure all roles use the optional global standards pattern with fallback defaults.

**Completed:**
- [x] k8s-tools role
- [x] common role
- [x] k8s role
- [x] group_vars/all/global.yaml path fix

**Remaining:**
- [ ] Audit all other roles for global variable usage
- [ ] Apply fallback pattern where needed

---

### Replace Hard-Coded Kubeconfig Paths
**Priority:** Medium
**Effort:** Low

Replace hard-coded `/etc/kubeconfig` references with variable lookups.

**Context:**
- A `global.kubeconfig` variable now exists in `group_vars/all/global.yaml`
- Roles should reference `{{ <role>_vars.global.kubeconfig }}` instead of hard-coding the path
- This follows the optional global standards pattern with fallback defaults

**Tasks:**
- [ ] Search for hard-coded `/etc/kubeconfig` references across all roles
- [ ] Replace with variable references (e.g., `k8s_vars.global.kubeconfig`)
- [ ] Ensure roles have the kubeconfig lookup with fallback in their defaults:
  ```yaml
  global:
    kubeconfig: "{{ lookup('ansible.builtin.vars', 'global').kubeconfig | default('/etc/kubeconfig') }}"
  ```

**Search command:**
```bash
grep -r "/etc/kubeconfig" roles/ --include="*.yaml"
```

---

### Remove Unused Global Attributes from Role Defaults
**Priority:** Low
**Effort:** Low

Reduce duplication by removing unused global attributes from role defaults.

**Context:**
- Roles currently include all global attributes in their defaults
- Many roles don't use all attributes (e.g., a role might not need `global.secrets`)
- Only include global attributes that the role actually uses

**Tasks:**
- [ ] Audit each role's tasks to identify which global attributes are actually used
- [ ] Remove unused global attributes from role defaults
- [ ] Examples of optimization:
  - If a role doesn't create files, it doesn't need `global.working`
  - If a role doesn't store secrets, it doesn't need `global.secrets`
  - If a role doesn't compile code, it doesn't need `global.source`

**Search command:**
```bash
# For each role, grep for global attribute usage in tasks
grep -r "global\.secrets" roles/*/tasks/ --include="*.yaml"
grep -r "global\.working" roles/*/tasks/ --include="*.yaml"
# etc.
```

---

### Migrate Legacy Configuration
**Priority:** Medium
**Effort:** Medium

Clean up and migrate configuration from deleted OS files.

**Tasks:**
- [ ] Migrate packages from deleted OS files to common role
- [ ] Migrate users/groups from deleted OS files to common role
- [ ] Replace hard-coded domain names with lan variable references

---

## Technical Debt

### Update Documentation
**Priority:** Low
**Effort:** Low

Keep documentation in sync with implementation.

**Tasks:**
- [ ] Document the k8s-engine abstraction pattern
- [ ] Add examples for Variable Merge Pattern usage
- [ ] Document custom facts (arch.fact) usage

---

## Features

### Multi-Distribution K8s Support
**Priority:** Low
**Effort:** Medium
**Status:** Partial

Complete the k8s-engine abstraction to fully support multiple Kubernetes distributions.

**Current State:**
- k8s-engine role created with RKE2 support
- CRC placeholder exists but not implemented

**Next Steps:**
- [ ] Implement CRC (CodeReady Containers) support
- [ ] Test distribution switching via group membership
- [ ] Document distribution selection in README

---

### Add Claude CLI Installation Role
**Priority:** Low
**Effort:** Low

Create a role to install Claude CLI as part of development tools.

**Context:**
- Claude CLI is a useful development tool
- Should be installed alongside other development tools (like k9s, helm)
- Can follow the same pattern as k8s-tools role

**Implementation:**
- Create `roles/claude-cli/` following the standard role structure
- Add to development play in playbook
- Include version management for Renovate tracking
- Use cross-platform architecture detection (ansible_local['arch']['container'])

**Tasks:**
- [ ] Create `roles/claude-cli/defaults/main.yaml` with version and URL
- [ ] Create `roles/claude-cli/tasks/main.yaml` with download/install logic
- [ ] Add global variable lookups with fallback defaults
- [ ] Add to appropriate playbook (development tools play)
- [ ] Test installation on multiple platforms

**Resources:**
- Follow pattern from `roles/k8s-tools/` for consistency
- Claude CLI releases: https://github.com/anthropics/anthropic-tools

---

### Add kubeseal CLI to Development Tools
**Priority:** Low
**Effort:** Low

Install kubeseal CLI for developers to encrypt Kubernetes secrets.

**Context:**
- `kubeseal` is the client-side CLI for sealed-secrets
- Used to encrypt secrets before committing to git
- Complements the sealed-secrets controller (which lives in k8s role)
- Developer tool, not cluster infrastructure

**Implementation:**
- Add to development tools role (or create k8s-dev-tools role)
- Follow same pattern as Helm/k9s installation
- Version tracking for Renovate

**Tasks:**
- [ ] Add kubeseal installation to appropriate dev tools role
- [ ] Include version management
- [ ] Use cross-platform architecture detection
- [ ] Test on multiple platforms

**Resources:**
- kubeseal releases: https://github.com/bitnami-labs/sealed-secrets/releases
- Follow pattern from `roles/k8s-tools/` for consistency

**Note:** The sealed-secrets **Controller** is separate and lives in the `k8s` role as cluster infrastructure.

---

## Notes

- Items are organized by category (Automation, Refactoring, Technical Debt, Features)
- Priority levels: High, Medium, Low
- Effort estimates: Low (< 1 hour), Medium (1-4 hours), High (> 4 hours)
- Status indicates work-in-progress items

---
Machine Learning Tools:

- Installed on Model Server:
  - apt install -y python3-huggingface-hub/questing
  - pip install hf_transfer
