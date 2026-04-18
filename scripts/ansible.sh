#! /bin/bash
# ============================================================================
# Usage: ansible.sh [OPTIONS]
#
#       --very-verbose          Enable rediculous logging
#   -f, --filter                Enable the output filter (i.e., only show TASK,
#                               PLAY, ok, warn, etc)
#   -n, --no-op                 Don't run Ansible, echo the command-line to
#                               STDOUT, then exit
#       --limit <host>          Limit the run to the specified host(s)
#                               May be used multiple times.
#       --tags <tag>            Limit the run to the specified tag(s)
#                               May be used multiple times.
#   -l, --log-file <file-path>  Capture the output to the specified file
#                               (file output is never filtered)
#   -t, --time                  Time the execution of the Ansible command
#   -h, --help                  Print this help screen and exit
# ----------------------------------------------------------------------------
export ANSIBLE_DEPRECATION_WARNINGS=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=false
export ANSIBLE_CALLBACK_RESULT_FORMAT=yaml

ANSIBLE_PLAYBOOK=ansible-playbook
ANSIBLE_VAULT_PASSWORD_FILE=${ANSIBLE_VAULT_PASSWORD_FILE:-~/.ansible-vault-password}
COLOR_ERROR=$'\033[1;31m'
COLOR_WARNING=$'\033[1;33m'
COLOR_INFO=$'\033[1;34m'
COLOR_SUCCESS=$'\033[1;32m'
COLOR_RESET=$'\033[0m'
DEFAULT_ANSIBLE_DIR=~/dev/kerrys-learning-lab/devsecops/ansible
DEFAULT_FILTER=^TASK\|^PLAY\|^ok\|^changed\|^failed\|^fatal
EXTRA_ANSIBLE_ARGS=()
FILTER=
INVENTORY=inventory
LIMIT=()
LOG_FILE=/dev/null
PLAYBOOK=westsidestreet.net.yaml
TAGS=()
TIME=
VERBOSE=

# ----------------------------------------------------------------------------
usage() {
    # awk '/^# =====/,/^# -----/' "$0" | sed 's/^# \?//'
    awk '/^# =====/{f=1; next} /^# -----/{exit} f' "$0" | sed 's/^# \?//'
    exit ${1:-1}
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE=-v
            shift
            ;;
        --very-verbose)
            VERBOSE=-vvv
            shift
            ;;
        -f|--filter)
            FILTER=${DEFAULT_FILTER}
            shift
            ;;
        -n|--no-op)
            ANSIBLE_PLAYBOOK="echo ${ANSIBLE_PLAYBOOK}"
            shift
            ;;
        --limit)
            LIMIT+=("$2")
            shift 2
            ;;
        --tags)
            TAGS+=("$2")
            shift 2
            ;;
        -l|--log-file)
            LOG_FILE=$2
            shift 2
            ;;
        -t|--time)
            TIME=time
            shift
            ;;
        -h|--help)
            usage 0
            shift
            ;;
        *)
            EXTRA_ANSIBLE_ARGS+=("$1")
            shift
            ;;
    esac
done

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

ANSIBLE_CMD=()
ANSIBLE_CMD+=(${TIME})
ANSIBLE_CMD+=(${ANSIBLE_PLAYBOOK})
ANSIBLE_CMD+=(${VERBOSE})
ANSIBLE_CMD+=(--inventory             ${INVENTORY})
ANSIBLE_CMD+=(--vault-password-file   ${ANSIBLE_VAULT_PASSWORD_FILE})
ANSIBLE_CMD+=(${PLAYBOOK})

if [[ ${#LIMIT[@]} -gt 0 ]]; then
    for host in "${LIMIT[@]}"; do
        ANSIBLE_CMD+=(--limit "${host}")
    done
fi
for tag in "${TAGS[@]}"; do
    ANSIBLE_CMD+=(--tags "${tag}")
done

stdbuf -oL ${ANSIBLE_CMD[@]} |& tee ${LOG_FILE} | while IFS= read -r line; do
    if [[ -z "${FILTER}" ]] || echo "${line}" | grep -q -E ${FILTER}; then
        LINE="${line}"
    else
        LINE=
    fi

    if [[ -n "${LINE}" ]]; then
        LINE=$(echo "${LINE}" | sed -E "s/\b(fatal|error|failed|ERROR)/${COLOR_ERROR}\1${COLOR_RESET}/g")
        LINE=$(echo "${LINE}" | sed -E "s/\b(TASK|PLAY)/${COLOR_INFO}\1${COLOR_RESET}/g")
        LINE=$(echo "${LINE}" | sed -E "s/\b(ok)/${COLOR_SUCCESS}\1${COLOR_RESET}/g")
        LINE=$(echo "${LINE}" | sed -E "s/\b(changed)/${COLOR_WARNING}\1${COLOR_RESET}/g")

        echo "${LINE}"
    fi
done
