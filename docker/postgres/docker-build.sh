#!/usr/bin/env bash

cd ../..

docker build -t sber/ai-kpi/postgres:16.9-bookworm -f docker/postgres/Dockerfile .