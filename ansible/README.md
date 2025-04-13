
cd ~/dev/devenv/ansible

ansible-playbook --extra-vars @config/vars.yaml -i ansible_hosts k8s-ecosystem-only-playbook.yaml

Facts from all hosts:
 ansible -i inventory/ all -m ansible.builtin.setup --tree /tmp/facts

 $ argocd login --insecure $(my-ip):30443