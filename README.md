# langchain-islo

[![PyPI - Version](https://img.shields.io/pypi/v/langchain-islo?label=%20)](https://pypi.org/project/langchain-islo/#history)
[![PyPI - License](https://img.shields.io/pypi/l/langchain-islo)](https://opensource.org/licenses/MIT)

[Islo](https://islo.dev) sandbox integration for [Deep Agents](https://github.com/langchain-ai/deepagents).

Islo provides long-running, reconnect-surviving AI sandboxes on real Linux VMs,
with pause/resume, snapshots, and a gateway layer for secret isolation and
egress policies.

## Install

```bash
uv add langchain-islo
# or: pip install langchain-islo
```

Set your API key (keys look like `ak_...`):

```bash
export ISLO_API_KEY="ak_..."
```

> **Sandbox image requirement.** The inherited filesystem tools (`read`, `write`,
> `edit`, `ls`, `glob`, `grep`) shell out to `python3` and GNU `grep` inside the
> sandbox. Use an image that provides them (e.g. `python:3.12-slim`, or
> `ubuntu`/`debian` with `python3` + `grep` installed). Alpine/BusyBox `grep`
> lacks the flags these tools need. Islo's default `islo-runner` image ships GNU
> `grep` but **not** `python3`, so pass an explicit image (e.g. `python:3.12-slim`).
>
> [`docker/Dockerfile`](docker/Dockerfile) builds an `islo-runner`-based image
> with `python3` added — the recommended sandbox image. The base is a
> `BASE_IMAGE` build arg (default `islo-runner:latest`); CI builds it against a
> public base to verify the `python3` + GNU `grep` contract:
>
> ```bash
> docker build --build-arg BASE_IMAGE=python:3.12-slim -f docker/Dockerfile .
> ```

## Usage

Wrap an existing Islo sandbox and use it as a Deep Agents backend:

```python
from islo import Islo
from langchain_islo import IsloSandbox

client = Islo()  # reads ISLO_API_KEY
sandbox = client.sandboxes.create_sandbox(image="python:3.12-slim")

backend = IsloSandbox(client=client, sandbox=sandbox)

result = backend.execute("echo hello")
print(result.output)  # "hello"

# Filesystem tools are inherited from BaseSandbox:
backend.write("/workspace/app.py", "print('hi')\n")
print(backend.read("/workspace/app.py").file_data["content"])
```

### Lifecycle helper

`IsloProvider` creates, attaches to, and deletes sandboxes for you:

```python
from langchain_islo import IsloProvider

provider = IsloProvider()  # reads ISLO_API_KEY
backend = provider.get_or_create(image="python:3.12-slim")
try:
    print(backend.execute("uname -a").output)
finally:
    provider.delete(sandbox_id=backend.id)
```

## What you get

`IsloSandbox` subclasses `deepagents.backends.sandbox.BaseSandbox`, so it
implements the full `SandboxBackendProtocol`:

| Method | Backed by |
| --- | --- |
| `execute()` | Islo `exec_in_sandbox` + result polling (commands run via `sh -c`) |
| `upload_files()` / `download_files()` | Islo sandbox files endpoint (raw bytes) |
| `ls` / `read` / `write` / `edit` / `glob` / `grep` | Inherited from `BaseSandbox` |
| `id` | Islo sandbox id |

Async variants (`aexecute`, `aupload_files`, `adownload_files`, ...) are provided
by the base class via thread offloading.

## Configuration

| Env var | Default | Purpose |
| --- | --- | --- |
| `ISLO_API_KEY` | — | Bearer token used to authenticate |
| `ISLO_BASE_URL` | `https://api.islo.dev` | Control-plane base URL |

## License

MIT
