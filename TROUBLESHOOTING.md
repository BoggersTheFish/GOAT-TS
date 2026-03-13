## Troubleshooting GOAT-TS

This guide collects common issues when running GOAT-TS locally on Windows, macOS, or Linux and how to fix them. It complements `README.md`, `PLATFORM.md`, and the inline error messages in scripts and the GUI.

Wherever possible, GOAT-TS fails **loudly with a clear exception message** rather than silently falling back. Use that message together with the sections below.

---

## 1. Python, virtualenv, and `pytest` not found

- **Symptom (Windows / PowerShell):**
  - `pytest : The term 'pytest' is not recognized...`
  - `ModuleNotFoundError` for `nebula3`, `torch`, `langchain`, etc.
- **Cause:** The virtual environment is not active or dependencies were not installed.
- **Fix:**
  - From the repo root:

    **Windows (PowerShell):**

    ```powershell
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    python -m pytest -q
    ```

    **macOS / Linux:**

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python -m pytest -q
    ```

  - If `Activate.ps1` is blocked on Windows, either:
    - Run PowerShell as Administrator and execute:

      ```powershell
      Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
      ```

    - Or use `python -m venv .venv` and run scripts via `.\.venv\Scripts\python ...` without activating.

---

## 2. Docker and ports (NebulaGraph, Redis, Spark)

- **Symptoms:**
  - `docker compose` reports port conflicts (ports already in use).
  - NebulaGraph connection errors such as `Failed to initialize NebulaGraph connection pool` or `Failed to use graph space`.
- **Default ports (from `docker/docker-compose.yml`):**
  - NebulaGraph meta: `9559`
  - NebulaGraph storage: `9779`
  - NebulaGraph graphd: `9669`
  - Redis: `6379`
  - Spark master: `7077` and UI `8080`
- **Fix:**
  1. Ensure Docker Desktop or your Docker daemon is running.
  2. From the repo root, start the stack:

     ```bash
     docker compose -f docker/docker-compose.yml up -d
     ```

  3. If ports are already in use, either:
     - Stop conflicting containers or local services on those ports, or
     - Edit `docker/docker-compose.yml` to map alternative host ports and update `configs/graph.yaml` (and any scripts) accordingly.
  4. After changes, restart:

     ```bash
     docker compose -f docker/docker-compose.yml down
     docker compose -f docker/docker-compose.yml up -d --build
     ```

---

## 3. NebulaGraph connection and schema errors

- **Symptoms:**
  - `NebulaGraph client init failed. Use --dry-run for in-memory.`
  - `Failed to initialize NebulaGraph connection pool.`
  - `Failed to use graph space 'ts_space'. Check Nebula connection and space name.`
- **Checklist:**
  1. Docker Nebula services are up (`ts-nebula-metad0`, `ts-nebula-storaged0`, `ts-nebula-graphd0`).
  2. `configs/graph.yaml` has correct host, port, username, password, and space.
  3. If you use a `.env` file, it does not override these with the wrong values.
- **Fix:**
  - For quick local experiments, prefer **dry-run**:

    ```bash
    python -m src.agi_loop.demo_loop --dry-run --seed-labels concept --ticks 5
    ```

  - For live mode:
    1. Start Docker as above.
    2. Run the schema application script:

       ```bash
       python scripts/apply_schema.py --live
       ```

    3. If this fails, inspect the full error message; it will usually indicate connection or authentication problems.
  - If you change Nebula ports or credentials, update both `configs/graph.yaml` and any relevant `.env` overrides (`NEBULA_HOST`, `NEBULA_PORT`, `NEBULA_USERNAME`, `NEBULA_PASSWORD`).

---

## 4. Java / Spark ETL (`run_spark_etl.py`)

- **Symptoms:**
  - `JAVA_HOME is not set` or Spark cannot start.
  - `pyspark` complains about the Java version.
- **Requirements:**
  - Java 8+ JDK installed.
  - `JAVA_HOME` pointing to the JDK install (not just the JRE).
- **Fix (macOS / Linux):**

  ```bash
  export JAVA_HOME=/path/to/your/jdk
  python scripts/run_spark_etl.py
  ```

- **Fix (Windows / PowerShell):**
  1. Install a JDK (e.g. Temurin or OpenJDK).
  2. Set `JAVA_HOME` in System Environment Variables, then restart your terminal:

     ```powershell
     $env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17"
     python scripts\run_spark_etl.py
     ```

  3. If Docker-based Spark is used, ensure the `spark` service in `docker/docker-compose.yml` is healthy.

---

## 5. LLM configuration (`configs/llm.yaml`)

- **Symptoms:**
  - Errors when running reasoning or ingestion that mention `TripleExtractor`, LangChain, or LLM keys.
  - Timeouts or 401/403 errors from external LLM providers.
- **Checklist:**
  - `configs/llm.yaml` exists and matches the provider you want (local vs remote).
  - Necessary environment variables or API keys are set (see comments in `llm.yaml`).
  - You are not accidentally using a cloud provider when you expect a fully local model.
- **Local-first tips:**
  - Prefer a local Hugging Face model or an Ollama/other local backend when possible.
  - Keep cloud LLMs optional and config-driven; do not hard-code provider-specific behavior into scripts.
- **Fix:**
  - Review `configs/llm.yaml` and set only the backends you intend to use.
  - If you see LLM-related errors in ingestion or reasoning, you can temporarily disable LLM-based extraction or reasoning in the relevant config until keys are properly set.

---

## 6. GPU / CUDA issues

- **Symptoms:**
  - PyTorch reports no CUDA devices when you expect GPU.
  - FAISS-GPU cannot be imported.
  - Gravity or simulation steps run slowly.
- **Configuration:**
  - GPU usage is controlled by:
    - `configs/simulation.yaml` (`use_gpu`, `faiss_gpu`, or similar flags), and
    - Environment variables such as `GOAT_USE_GPU=1`.
- **Fix:**
  1. Verify your NVIDIA driver and CUDA toolkit are installed and compatible with the PyTorch version in `requirements.txt`.
  2. In Python, run:

     ```python
     import torch
     print(torch.cuda.is_available())
     print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "no device")
     ```

  3. If CUDA is not available, either:
     - Install a CUDA-enabled PyTorch build that matches your driver, or
     - Set the simulation config to CPU-only (disable GPU flags) and re-run the demo.
  4. If FAISS-GPU fails to import, either install the appropriate `faiss-gpu` wheel or configure the system to use `faiss-cpu` only.

---

## 7. Streamlit GUI and API server

- **Symptoms:**
  - GUI does not open in the browser or fails immediately.
  - API server endpoints return connection refused.
- **GUI checklist:**
  - From the repo root, with your virtual environment active:

    ```bash
    python -m streamlit run scripts/goat_ts_gui.py
    ```

  - Check the terminal output for the URL (e.g. `http://localhost:8501`) and open it in a browser.
  - If the port is already in use, either:
    - Stop the process using port `8501`, or
    - Use `--server.port` to choose another port:

      ```bash
      python -m streamlit run scripts/goat_ts_gui.py -- --server.port 8502
      ```

- **API server checklist:**

  ```bash
  uvicorn scripts.serve_api:app --reload --host 0.0.0.0 --port 8000
  ```

  - If `uvicorn` is not found, ensure your virtual environment is active and `requirements.txt` is installed.
  - If port `8000` is in use, pick another port and update your client calls.

---

## 8. Tests and benchmarks

- **Running tests:**

  ```bash
  python -m pytest -q
  ```

  - On Windows, always prefer the `python -m pytest` form from the activated environment.
  - If specific tests fail (e.g. graph benchmarks), read the test name and error message; many tests assume Docker services or certain configs are available.

- **Common causes of test failures:**
  - Docker stack is not running for tests that require NebulaGraph or Redis.
  - `JAVA_HOME` not set for Spark-related tests.
  - LLM configuration missing for extraction or reasoning tests.

If you encounter an error that is not covered here, capture:

- Your OS and Python version,
- The exact command you ran,
- The full stack trace or error message,

and open an issue or PR with a reproducible snippet so the behavior can be improved.

