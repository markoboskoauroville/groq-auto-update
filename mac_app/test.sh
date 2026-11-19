#!/bin/sh
# test.sh: offline tests for Queen's Swift API and Python backend proxy.
set -e
cd "$(dirname "$0")"
mkdir -p build
swiftc -swift-version 5 -o build/queen-tests app/core/*.swift tests/*.swift
./build/queen-tests
