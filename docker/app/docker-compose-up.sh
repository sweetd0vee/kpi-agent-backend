#!/bin/bash


export COMPOSE_PROJECT_NAME=ai-kpi

docker-compose -f docker-compose.yml --env-file .env up -d