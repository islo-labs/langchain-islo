# langchain-islo

[![PyPI - Version](https://img.shields.io/pypi/v/langchain-islo?label=%20)](https://pypi.org/project/langchain-islo/#history)
[![PyPI - License](https://img.shields.io/pypi/l/langchain-islo)](https://opensource.org/licenses/MIT)

[Islo](https://islo.dev) sandbox integration for [Deep Agents](https://github.com/langchain-ai/deepagents).

Islo provides long-running, reconnect-surviving AI sandboxes on real Linux VMs,
with pause/resume, snapshots, and a gateway layer for secret isolation and
egress policies.

## Install

```bash
pip install langchain-islo
```

Set your API key (keys look like `ak_...`):

```bash
export ISLO_API_KEY="ak_..."
```

## Usage

Wrap an existing Islo sandbox and use it as a Deep Agents backend:

```python
from islo import Islo
from langchain_islo import IsloSandbox

client = Islo()  # reads ISLO_API_KEY
sandbox = client.sandboxes.create_sandbox(image="ubuntu:24.04")

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
backend = provider.get_or_create(image="ubuntu:24.04")
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
