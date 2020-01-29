#!/bin/bash

if [[ $# != 1 ]]; then
    Usage: "$(basename $0) <dir>"
    exit 1
fi

find "$1" -name 'DSCF*.MOV' -exec fuji.py auto-convert {} \;

