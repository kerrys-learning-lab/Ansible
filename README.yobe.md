# Good Luck!

## 1. Overview

### 1.1 How to Translate What You're Seeing

- My home network is called `westsidestreet.net`.

  - **So, the top-level Ansible playbook at `./westsidestreet.net.yaml` is
    the Playbook that configures my entire home-lab.**

  - You probably want to make a copy of that for yourself and trim it down
    to make it easier to focus on what you want to start with.

- `elitedesk` is the hostname of the machine on my network that is Running
  GitLab.

  - So, the variables/vars at `./host_vars/elitedesk/*` configure that machine.

  - You **specifically** want to look at the `./host_vars/elitedesk/gitlab.yaml`
    file

  - Ansible includes other variables from (e.g.) `./group_vars/all` and merges
    all the variables together.

- My LAN DNS server is `192.168.0.3`

- Other hosts on my network (just so you recognize the names when you see them
  in the Ansible files)

  - `dev-vm` - the Linux VM that I use for development.
  - `nvidia-5080` - the Linux VM that has my main GPU.
  - I have some Raspberry Pi hosts listed, but I haven't been doing much with
    those lately, so the scripts are probably broken. I suggest staying away
    from them

- All of my secrets are in `./group_vars/all/secrets.yaml`.

  - This allows me to consolidate the secrets in one location that I
    "protect"

  - I have other variables files do a "lookup" of the actual secrets.  That
    way, the secret is "pulled" into the correct data structure that the
    task needs.

    Example:
    - `./group_vars/all/secrets_vault.yaml` defines `secrets_vault.gitlab.glpat.username`
    - `./host_vars/dev-vm/rke2.yaml` uses it by doing the `lookup`

  - Refer to the `secrets.yaml` file to determine how variables are used, but
    YOU DO NOT HAVE TO ENCRYPT YOUR SECRETS to use Ansible.  If you prefer,
    just replace the encrypted strings with free-text.  Ansible will work the
    same way.


### 1.2 Ansible Reminders

- Playbooks are the top-level instructions.  Again, look at `./westsidestreet.net.yaml`
  as the "entry-point"

- Inventory organizes the hosts into groups and provides information for how Ansible
  should connect to those hosts.  Check the `./inventory` directory.

- Generally speaking, variables are in `group_vars` and `host_vars`.  Roles can
  also provide default values for variables.

- Roles organize groups of tasks (see `./roles`).  Each role has a
  `<role>/tasks` subdirectory.  Optional subdirectories in a role include
  `<role>/handlers` which are asynchronous/optional steps that can be triggered
  by a task and `<role>/defaults` which are default variable values which
  have the lowest precedence (can be overridden by host/group vars)

### 2.1 Specific Roles of Interest

Obviously, you will want the GitLab role.

**However**, due to my "design decisions" regarding the GitLab configuration,
you should start with some pre-requisite roles, assuming you make the same
decisions:

- I use local K8s volumes for a lot of the GitLab data (because databases don't
  like to be run from network shares).  So, you will want the `k8s-local-volumes`
  role to run successfully.

- I use Helm to install the Operator's chart. The installation of the
  Helm CLI is automated by the `helm-cli` role

- It looks like a lot of my Ansible code explicitly wants the Kubeconfig file
  to connect to the cluster to be at `/etc/kubeconfig`.  You can either create
  a link so that the Kubeconfig *is* there, or you can search/replace to point
  Ansible to the correct location for your environment.

## 2. Running Ansible

### K8s Local Volumes Role

#### Description

This role creates directories on the target host and configures K8s to be able
to use those directories as volumes.

#### Inputs

The role looks for the variable `k8s_local_volumes` to determine what directories
and volumes to create.

For my GitLab host (`elitedesk`), the `k8s_local_volumes` variable is defined in
`./host_vars/elitedesk/k8s-local-volumes.yaml`.  If you look in there, you can
see several GitLab-themed volumes.

#### What should happen when this task executes:

1. Task *Create K8s Local Storage Class* creates the `local` storage class
   in Kubernetes.

2. Task *Create Local Kubernetes Volume Root Directories* creates the root
   directory under which local volumes are organized

3. Task *Create Local Kubernetes Volume Directory Parents* creates a top-level
   subdirectory for each role that uses `k8s-local-volumes`.  In the
   example below, `gitlab` is the parent.  **TODO**: I thought Ansible would
   create parents automatically... investigate.

4. Task *Create Local Kubernetes Volume Directories* creates the actual
   local volume directories.

5. Task *Create Local Kubernetes Volume(s)* creates a K8s volume pointing to
   the applicable directory.


```
$ tree -L 2 /var/lib/k8s-local-pv/gitlab/
/var/lib/k8s-local-pv/gitlab/
├── dependabot
│   └── mongodb
├── gitaly
│   ├── +gitaly
│   └── @hashed
└── postgresql
    └── data
```

**NOTE**: The change to having a separate role do the local volumes is
          relatively recent.  So, if you see other places in the code that
          create their own local volume, it's probably a left-over.

### Helm CLI Role

### GitLab Role

What should happen:

1. Task: *Install/Configure GitLab Operator via Helm* installs the GitLab
   Operator Helm chart into the `gitlab-system` Namespace (which should
   be created automatically)

2. Task: *Wait for GitLab Operator to be Installed (flush handlers)*
   Ansible delays (one minute) to allow time for the operator to be installed.

3. I have commented out the *Create GitLab Backup Secret* task for now.
   You will want to back-up your data at some point, but at least
   for me, I got the installation working first, then went back and enabled
   more features.  Being able to do the updates with Ansible helps.

4. I've had the *Create GitLab Registry PostgreSQL Secret* task commented out
   for a while now.  IIRC, you won't need it - I used it for recovering from
   backup a while ago.  You can always un-comment it if something fails and
   complains about the Postgres password.

5. Task: *Create Local Kubernetes Claim(s) for GitLab* Creates the K8s volumes
   for GitLab using the local storage class and local directories created by
   the `k8s-local-volumes` role.

6. Task: *Apply GitLab CRD* finally creates the GitLab instance.
   The "settings" for the CRD come from `./host_vars/elitedesk/gitlab.yaml`
