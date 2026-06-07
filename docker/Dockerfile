# Sandbox image for langchain-islo + Deep Agents.
#
# Deep Agents' BaseSandbox filesystem tools (read/write/edit/ls/glob) run via
# `python3`, and `grep` requires GNU grep. Islo's default `islo-runner` image
# ships GNU grep but NOT python3, so this image guarantees both (plus a few
# common agent tools) and is safe to use as the Islo sandbox image.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git curl ca-certificates grep coreutils \
 && rm -rf /var/lib/apt/lists/*

# python3, python, and GNU grep are all present.
CMD ["sleep", "infinity"]
