# Extensions and plugins

GOAT-TS stays modular so you can extend it without forking.

---

## Plugin system (Stage 9)

Optional modules can register **hooks** that are called at certain points (e.g. after a reasoning run). To enable a plugin:

1. Add a module under `src/plugins/` that defines a `PLUGIN_HOOKS` dict mapping hook names to callables.
2. List the module name in `configs/plugins.yaml` under `plugins.enabled`.

Example: `src/plugins/example_hook.py` defines `on_reasoning_done`. The loader is in `src/plugins/__init__.py` (`load_plugin`, `load_all_plugins`).

---

## Community / example extensions

| Extension | Description |
|-----------|-------------|
| **Connectors** | `src/ingestion/connectors.py` — RSS, URL list ingestion. Configure in `configs/ingestion_sources.yaml`. |
| **Example apps** | `scripts/app_qa_bot.py` (Q&A loop), `scripts/app_knowledge_explorer.py` (query → subgraph JSON). |
| **Presets** | `configs/presets.yaml` — CLI presets (quick-demo, full-demo, lightweight). Use `--preset` with demo_loop or one_click_demo. |
| **Reasoning output** | API `POST /reasoning` with `output_format: "app"` returns full JSON for apps (activated_nodes, graph_context, hypotheses). |

If you build something on top of GOAT-TS (e.g. a custom connector or dashboard), open an issue or PR to add it to this list.
