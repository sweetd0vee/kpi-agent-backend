#!/bin/bash


export COMPOSE_PROJECT_NAME=ai-kpi-be

docker-compose -f docker-compose.yml --env-file .env down