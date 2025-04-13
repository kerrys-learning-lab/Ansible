#!/bin/bash

ARCH=$(dpkg --print-architecture)

JSON=$(cat <<EOF
{
    "arch": "${ARCH}"
}
EOF
)

echo ${JSON}
