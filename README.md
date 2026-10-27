# BeeAgent

**A modular Python runtime for automation, AI-assisted workflows, and domain-specific agents.**

BeeAgent provides the shared infrastructure for running independent modules with consistent configuration, execution controls, state management, and structured results.

Instead of building a separate application for every use case, you build a domain module and run it through BeeAgent.

## Architecture

```text
CLI / Web / Telegram
         |
    BeeAgent Core
         |
    Domain Modules
         |
  Scoped Capabilities
         |
 External Systems
```

**BeeAgent Core** handles orchestration, configuration, module loading, authorization, AI providers, logging, and artifacts.

**Domain modules** implement business or security-specific logic.

**Capabilities** provide controlled access to external APIs, tools, and isolated execution environments.

A module can request an operation, but it does not automatically receive permission to execute it.

## Modules

BeeAgent currently integrates three domain modules:

| Module                                                      | Description                                                                                                                       |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **[BeeScan](https://github.com/beesyst/beescan)**           | Authorized web security assessments, reconnaissance, vulnerability detection, evidence collection, and AI-assisted investigation. |
| **[BeeDrill](https://github.com/beesyst/beedrill)**         | Solana security testing, isolated execution scenarios, and regression analysis.                                                   |
| **[BeeAgent ROP](https://github.com/beesyst/beeagent-rop)** | Sales workflow automation, inbound lead classification, duplicate detection, CRM reconciliation, and AI-assisted triage.          |

Each module is a separate Python package. Modules can be installed and enabled independently through the runtime configuration.

BeeAgent can support additional modules without moving their domain logic into the core.

## Quick Start

### Requirements

- Python 3.14+
- Linux (recommended for native security workflows)
- Git
- `uv` (automatically bootstrapped by `start.sh` if missing)
- Access to the configured module dependencies

### Installation

```bash
git clone https://github.com/beesyst/beeagent.git
cd beeagent
```

Configure the required settings and credentials. The startup script creates `.env` from `.env.example` when needed. External API keys must be provided separately.

### Start the Web Console

```bash
./start.sh web
```

Default local address: `http://127.0.0.1:8000`

The console provides authenticated access to runtime information, modules, runs, and artifacts.

### Start Telegram

```bash
./start.sh telegram
```

Telegram requires the appropriate bot configuration and credentials.

## CLI

All workflows use the same entrypoint:

```bash
./start.sh <command>
```

Common commands:

```bash
./start.sh web
./start.sh telegram
./start.sh routes
```

Module-specific examples:

```bash
# Sales workflows
./start.sh rop poll

# Solana security regression
./start.sh beedrill check

# Web security assessment
./start.sh beescan bootstrap
./start.sh beescan assess

# AI-assisted web investigation
./start.sh beescan
./start.sh beescan investigate --target https://authorized.example --task 'Identify framework version'
./start.sh beescan investigate TASK.json
```

Module commands require their corresponding modules to be enabled. Security assessments and external operations also require explicit authorization and valid execution prerequisites.

See the module-specific guides for configuration and supported operations.

BeeScan direct and interactive intake require the one-time, default-disabled `beescan.investigation.trusted_local_enabled` setting and a permitted target. The legacy task-file command retains its independent configured approval. See [trusted local CLI operation](docs/product/beescan_guide.md#bs-9-trusted-local-operator-cli) for authority, prerequisites, limits and result semantics.

## Configuration

The main configuration file is:

```text
config/settings.yml
```

It controls module registration, runtime settings, integrations, execution policies, and AI profiles.

Secrets belong in environment variables or `.env`, not in the YAML configuration.

### AI Providers

BeeAgent supports OpenAI Responses and OpenAI-compatible providers, including OpenRouter and DeepSeek.

A shared AI profile resolver allows different modules to select different providers:

```yaml
ai:
  default_profile: openrouter
```

Individual modules can override the default using their `ai_profile` setting.

AI assistance is optional. Model output is validated and does not grant additional execution authority.

## Module Development

Modules implement a small contract defined by BeeSDK:

```python
class ModuleContract(Protocol):
    @property
    def module_id(self) -> str: ...

    @property
    def authority(self) -> AuthorityLevel: ...

    def supported_case_types(self) -> list[str]: ...

    def handle(self, context: ModuleContext) -> ModuleResult: ...
```

BeeAgent supplies runtime context, artifact access, and approved capabilities.

Domain models, rules, classification, and recommendations belong in the module. Shared infrastructure belongs in BeeAgent Core.

See [Architecture](docs/ARCHITECTURE.md) for details.

## Artifacts

Runs produce structured evidence under `storage/`, including execution results, reports, logs, and module-specific artifacts.

```text
storage/
├── runs/
├── artifacts/
├── reports/
└── interfaces/
```

Artifacts support debugging, reproducibility, and operator review. Sensitive credentials and unrestricted external data must not be included in public outputs.

## Development

Run the test suite from a prepared development environment:

```bash
uv run --frozen --no-sync pytest -q
```

The full development profile requires its configured dependencies, including the local `beeagent-rop` checkout.

Development follows a simple workflow:

`Roadmap → Issue → Code → Tests → Review → PR → Merge`

## Project Structure

```text
beeagent/
├── config/                 # Settings and startup
├── docs/                   # Architecture and guides
├── src/beeagent_module/
│   ├── core/               # Runtime and shared services
│   ├── integrations/       # Module integrations
│   ├── cases/              # Application workflows
│   ├── cli/                # Commands
│   └── interfaces/         # User-facing adapters
├── tests/
├── integration_tests/
├── storage/
├── start.sh
├── pyproject.toml
└── uv.lock
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Developer Guide](docs/DEV_GUIDE.md)
- [Security](docs/SECURITY.md)
- [Web Console](docs/WEB_UI.md)
- [BeeScan Operations](docs/product/beescan_guide.md)
- [Roadmap](docs/ROADMAP.md)
- [BeeSDK](https://github.com/beesyst/beesdk)

---

**BeeAgent runs the workflows. Modules provide the domain logic. Capabilities connect them to external systems.**
