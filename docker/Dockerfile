# Sandbox image for langchain-islo + Deep Agents, built on Islo's runner.
#
# Deep Agents' BaseSandbox filesystem tools (read/write/edit/ls/glob) run via
# `python3`, and `grep` requires GNU grep. The islo-runner base ships GNU grep
# but not python3, so this image adds python3 on top of it — keeping all of
# islo-runner's capabilities.
#
# The base image is a build arg so this can be verified against a public base
# (e.g. `--build-arg BASE_IMAGE=python:3.12-slim`) in CI, while the default
# builds on `islo-runner` in Islo's infra where that image is pullable.
ARG BASE_IMAGE=islo-runner:latest
FROM ${BASE_IMAGE}

# Ensure python3 is present, regardless of the base distro.
RUN set -eux; \
    if command -v apt-get >/dev/null 2>&1; then \
        apt-get update && apt-get install -y --no-install-recommends python3 \
        && rm -rf /var/lib/apt/lists/*; \
    elif command -v apk >/dev/null 2>&1; then \
        apk add --no-cache python3; \
    elif command -v microdnf >/dev/null 2>&1; then \
        microdnf install -y python3 && microdnf clean all; \
    elif command -v dnf >/dev/null 2>&1; then \
        dnf install -y python3 && dnf clean all; \
    else \
        echo "no supported package manager to install python3" >&2; exit 1; \
    fi; \
    # Verify the contract Deep Agents relies on: python3 + GNU grep.
    python3 --version; \
    grep --version | head -1
