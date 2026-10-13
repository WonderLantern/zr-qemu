#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu
cd "$(dirname "$0")/.."
python3 -B -m unittest discover -s tests -v
test_binary=$(mktemp)
trap 'rm -f "$test_binary"' EXIT HUP INT TERM
cc -std=c11 -O2 -Wall -Wextra -Werror tests/test_pixels.c $(pkg-config --cflags --libs glib-2.0) -lm -o "$test_binary"
"$test_binary"
