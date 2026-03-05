#!/usr/bin/env bash

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"

docker build -t ai-kpi-be -f "$repo_root/docker/app/Dockerfile" "$repo_root"