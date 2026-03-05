#!/bin/bash


export COMPOSE_PROJECT_NAME=sokol-be

docker-compose -f docker-compose.yml --env-file .env up -d