# Sandbox image for langchain-islo + Deep Agents, built on Islo's runner.
#
# Deep Agents' BaseSandbox filesystem tools (read/write/edit/ls/glob) run via
# `python3`, and `grep` requires GNU grep. The islo-runner base ships GNU grep
# but not python3, so this image adds python3 on top of it — keeping all of
# islo-runner's capabilities.
#
# NOTE: islo-runner lives in Islo's registry; build this where that base image
# is pullable (e.g. Islo CI). Adjust the tag/registry of the FROM line to match.
FROM islo-runner:latest

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
    python3 --version
