#!/usr/bin/env bash

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"

docker build -t sber/sokol-be:master -f "$repo_root/docker/app/Dockerfile" "$repo_root"