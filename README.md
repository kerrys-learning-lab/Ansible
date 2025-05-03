
### Prerequisites

  - https://docs.rke2.io/install/quickstart
    curl -sfL https://get.rke2.io | sudo sh -


cd ~/dev/devenv/ansible

```
ansible-playbook --inventory inventory westsidestreet.net.yaml
```

Facts from all hosts:
 ansible -i inventory/ all -m ansible.builtin.setup --tree /tmp/facts

