# Docs PR to `langchain-ai/docs`

> Do this **after** `langchain-islo` is published to PyPI. The maintainers
> (issue #3777) only accept docs PRs for *already-published* sandbox packages.

## 1. Add the integration page

Copy [`islo.mdx`](./islo.mdx) to:

```
src/oss/python/integrations/sandboxes/islo.mdx
```

This mirrors the structure of the existing `daytona.mdx` / `modal.mdx` /
`runloop.mdx` pages (Installation → Create a sandbox backend → Use with Deep
Agents → Cleanup).

## 2. Register it in the index

In `src/oss/python/integrations/sandboxes/index.mdx`, add an Islo card to the
grid (alphabetical-ish, alongside the others):

```mdx
<a href="/oss/integrations/sandboxes/islo" className="flex items-center justify-center gap-1.5 p-2 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 no-underline">
    <img className="block dark:hidden w-5 h-5" src="/images/providers/light/islo.svg" alt="" />
    <img className="hidden dark:block w-5 h-5" src="/images/providers/dark/islo.svg" alt="" />
    <span className="font-semibold">Islo</span>
</a>
```

## 3. Add the provider logo

Add light/dark SVGs (the index references both):

```
src/images/providers/light/islo.svg
src/images/providers/dark/islo.svg
```

(Check `docs.json` / the nav config for whether the new page must also be listed
in the sidebar navigation — grep for `daytona` to find every place it's
referenced and add `islo` in the same spots.)

## 4. Open the PR

Title: `docs: add Islo sandbox integration`

Body: link the published PyPI package (`https://pypi.org/project/langchain-islo/`)
and the issue (`langchain-ai/deepagents#3777`), and note it follows the
[sandbox contributing guide](https://docs.langchain.com/oss/python/contributing/implement-langchain#sandboxes).
