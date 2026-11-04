#!/bin/sh
# No secret is accepted as an argument, written to disk, or printed.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
cache_dir="$HOME/.local/share/maeum-keychain-helper"
umask 077
mkdir -p "$cache_dir"
chmod 700 "$cache_dir"
binary="$cache_dir/claude-keychain"
source_file="$script_dir/claude_keychain.swift"
if [ ! -x "$binary" ] || [ "$source_file" -nt "$binary" ]; then
    /usr/bin/swiftc "$source_file" -framework Security -o "$binary.new"
    chmod 700 "$binary.new"
    mv "$binary.new" "$binary"
fi
exec "$binary" "$@"
