#!/bin/bash

docker-compose down
docker-compose pull
docker-compose -f docker-compose.yml up -d
docker-compose logs -f
