#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

if [[ $# != 1 ]]; then
    Usage: "$(basename $0) <dir>"
    exit 1
fi

find "$1" -name 'DSCF*.MOV' -exec "${DIR}/fuji.py" auto-convert {} \;

