#!/usr/bin/env bash
#
# Pre-commit hook: Validate that every version: field with a semver-like value
# in Ansible defaults and vars files has a # renovate: comment above it.
#
# This ensures new dependencies are annotated for Renovate to track.
#
set -euo pipefail

exit_code=0

check_file() {
    local file="$1"
    local prev_line=""
    local line_num=0

    while IFS= read -r line; do
        line_num=$((line_num + 1))

        # Match lines like:  version: 1.2.3  or  version: "v1.2.3"  or  version: 'v0.1.0'
        # Skip commented-out version lines (like "# version: 2.25.1")
        if echo "$line" | grep -qP '^\s+version:\s+["\047]?v?\d+\.\d+' && \
           ! echo "$line" | grep -qP '^\s*#'; then
            # Check that the previous non-blank line is a # renovate: comment
            if ! echo "$prev_line" | grep -qP '^\s*#\s*renovate:'; then
                echo "ERROR: $file:$line_num: missing '# renovate:' annotation above:"
                echo "       $line"
                exit_code=1
            fi
        fi

        # Track previous non-blank line
        if [[ -n "${line// /}" ]]; then
            prev_line="$line"
        fi
    done < "$file"
}

# If arguments are provided, check only those files (pre-commit passes staged files)
# Otherwise, scan all target directories
if [[ $# -gt 0 ]]; then
    files=("$@")
else
    files=()
    while IFS= read -r -d '' f; do
        files+=("$f")
    done < <(find roles/*/defaults -name 'main.yaml' -print0 2>/dev/null)
    while IFS= read -r -d '' f; do
        files+=("$f")
    done < <(find host_vars -name '*.yaml' -print0 2>/dev/null)
    while IFS= read -r -d '' f; do
        files+=("$f")
    done < <(find group_vars -name '*.yaml' -print0 2>/dev/null)
fi

for file in "${files[@]}"; do
    # Only check files matching our target patterns
    case "$file" in
        roles/*/defaults/main.yaml|host_vars/*.yaml|host_vars/**/*.yaml|group_vars/*.yaml|group_vars/**/*.yaml)
            check_file "$file"
            ;;
    esac
done

if [[ $exit_code -ne 0 ]]; then
    echo ""
    echo "Add a '# renovate:' comment above each version field. Example:"
    echo "  # renovate: datasource=helm registryUrl=https://charts.example.io depName=my-chart"
    echo "  version: 1.2.3"
fi

exit $exit_code
