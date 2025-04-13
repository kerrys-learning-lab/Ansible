
cd ~/dev/devenv/ansible

```
ansible-playbook --inventory inventory westsidestreet.net.yaml
```

Facts from all hosts:
 ansible -i inventory/ all -m ansible.builtin.setup --tree /tmp/facts

