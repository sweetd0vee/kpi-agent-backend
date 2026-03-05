# Use a specific version of a Debian-based image for stability and compatibility.
# 'bookworm' is the latest stable Debian release.
FROM postgres:16.9-bookworm

# Copy the initialization script into the entrypoint directory.
# Scripts in this directory are automatically executed on first run.
COPY ./docker/postgres/init_db.sh /docker-entrypoint-initdb.d/01-init-dbs.sh

# The entrypoint script will handle execution permissions,
# but setting it explicitly is good practice.
RUN chmod +x /docker-entrypoint-initdb.d/01-init-dbs.sh