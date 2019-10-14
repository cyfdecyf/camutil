#!/bin/bash

find . -name 'DSCF*.MOV' -exec fuji.py auto-convert {} \;
