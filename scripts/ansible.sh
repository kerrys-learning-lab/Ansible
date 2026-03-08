#! /bin/bash

export ANSIBLE_DEPRECATION_WARNINGS=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=false
export ANSIBLE_CALLBACK_RESULT_FORMAT=yaml

ANSIBLE_CMD=ansible-playbook
DEFAULT_ANSIBLE_DIR=~/dev/kerrys-learning-lab/development-environment/ansible
ANSIBLE_VAULT_PASSWORD_FILE=${ANSIBLE_VAULT_PASSWORD_FILE:-~/.ansible-vault-password}
INVENTORY=inventory
PLAYBOOK=westsidestreet.net.yaml

# Allow execution from any location that has the Playbook (supports running
# from within Git worktrees)
if [[ ! -f ${PLAYBOOK} ]]; then
    echo "======================================================================================================"
    echo "Using default Ansible directory: ${DEFAULT_ANSIBLE_DIR}"
    echo "------------------------------------------------------------------------------------------------------"
    echo "This may not be what you want!"
    echo "======================================================================================================"
    echo ""
    cd ${DEFAULT_ANSIBLE_DIR}
fi

mkdir -p ./artifacts

time    ${ANSIBLE_CMD}  -vvv  \
                        --inventory             ${INVENTORY}  \
                        --vault-password-file   ${ANSIBLE_VAULT_PASSWORD_FILE}  \
                        $*  \
                        ${PLAYBOOK}  \
        | tee artifacts/ansible.log  \
        | grep -E ^TASK\|^PLAY\|^ok\|^changed\|^failed\|^fatal
