#!/bin/bash
# Wrapper for sign-all-ports.py — asks for the signify passphrase once and
# reuses it in memory for every port. Run this yourself in a real terminal:
#   ./sign-all-ports.sh
exec python3 "$(dirname "$(readlink -f "$0")")/sign-all-ports.py"
