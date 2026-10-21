# AGENTS

## Guidelines

- **Keep changes minimal and focused.** Only modify code directly related to the task at hand. Do not refactor unrelated code, rename existing variables or functions for style, or bundle unrelated fixes into the same commit or PR.
- **Do not add, remove, or update dependencies** unless the task explicitly requires it.

## Pre-Commit Checklist

Before every commit, run **all** of the following checks and ensure they pass:

### 1. Formatting

Before committing, always run `gofmt` and `goimports` on all modified files:

```sh
gofmt -w <modified files>
goimports -w <modified files>
```

### 2. Build All Commands

Verify that all tools compile successfully:

```sh
make all
```

This builds all executables under `cmd/`, including `keeper` which has special build requirements.

### 3. Tests

While iterating during development, use `-short` for faster feedback:

```sh
go run ./build/ci.go test -short
```

Before committing, run the full test suite **without** `-short` to ensure all tests pass, including the Ethereum execution-spec tests and all state/block test permutations:

```sh
go run ./build/ci.go test
```

### 4. Linting

```sh
go run ./build/ci.go lint
```

This runs additional style checks. Fix any issues before committing.

### 5. Generated Code

```sh
go run ./build/ci.go check_generate
```

Ensures that all generated files (e.g., `gen_*.go`) are up to date. If this fails, first install the required code generators by running `make devtools`, then run the appropriate `go generate` commands and include the updated files in your commit.

### 6. Dependency Hygiene

```sh
go run ./build/ci.go check_baddeps
```

Verifies that no forbidden dependencies have been introduced.

## What to include in commits

Do not commit binaries, whether they are produced by the main build or byproducts of investigations.

## Commit Message Format

Commit messages must be prefixed with the package(s) they modify, followed by a short lowercase description:

```
<package(s)>: description
```

Examples:
- `core/vm: fix stack overflow in PUSH instruction`
- `eth, rpc: make trace configs optional`
- `cmd/geth: add new flag for sync mode`

Use comma-separated package names when multiple areas are affected. Keep the description concise.

## Pull Request Title Format

PR titles follow the same convention as commit messages:

```
<list of modified paths>: description
```

Examples:
- `core/vm: fix stack overflow in PUSH instruction`
- `core, eth: add arena allocator support`
- `cmd/geth, internal/ethapi: refactor transaction args`
- `trie/archiver: streaming subtree archival to fix OOM`

Use the top-level package paths, comma-separated if multiple areas are affected. Only mention the directories with functional changes, interface changes that trickle all over the codebase should not generate an exhaustive list. The description should be a short, lowercase summary of the change.

---

The sections below were added for the sandbox triage agent. Everything above is
go-ethereum's own `AGENTS.md` at snapshot `7a73ffe`, unchanged. Procedures belong in
`.claude/skills/`, and hard limits in the workflow's permissions and safe outputs, not here.

## Project structure

| Path | What lives there |
|---|---|
| `cmd/` | executables: `geth` (the client), `clef` (signer), `evm` (incl. `t8n`), `devp2p`, `abigen`, `blsync`, `era`, `keeper`, `utils` (CLI flags) |
| `core/` | chain import (`blockchain*.go`), state transition, `vm/`, `state/`, `txpool/` (`legacypool`, `blobpool`), `types/` (incl. `bal/` block access lists), `rawdb/`, `filtermaps/` (log index) |
| `eth/` | the `eth` service: `downloader/`, `syncer/`, `fetcher/`, `filters/` (logs and subscriptions), `catalyst/` (Engine API), `tracers/`, `gasprice/` |
| `internal/ethapi/` | most JSON-RPC methods (`eth_call`, `eth_simulateV1`, `eth_estimateGas`, overrides) |
| `node/`, `rpc/` | node lifecycle and HTTP, WebSocket and IPC endpoints, plus the RPC framework |
| `p2p/` | devp2p networking, discovery v4/v5, ENR, NAT, dialing |
| `triedb/`, `trie/`, `ethdb/` | state storage (`pathdb`, `hashdb`), Merkle tries, LevelDB/Pebble backends |
| `beacon/` | light client (`blsync`), Engine API types |
| `accounts/`, `crypto/`, `signer/` | wallets, `abi/` and `abigen`, cryptography (`bn256`, `kzg4844`, `secp256k1`) |
| `params/`, `version/` | chain configs and forks; the current version is in `version/version.go` |
| `build/` | `ci.go` (build, test, lint, release packaging including the Ubuntu PPA) |
| `docs/` | audit reports and postmortems only (user docs live at geth.ethereum.org) |
| `.github/ISSUE_TEMPLATE/` | the three issue templates described below |

## Build and test

Use the checklist above: `make all`, `go run ./build/ci.go test -short`, then the full
`go run ./build/ci.go test`, `lint`, `check_generate` and `check_baddeps`. Go version: see
`go.mod`. The triage scripts are plain Python 3 (standard library only):

```sh
python3 -m unittest discover -s .claude/skills/geth-issue-triage/tests
```

In this sandbox the `testdata/` fixture directories were removed, so fixture-based Go tests
fail. The triage agent never builds or tests anything.

## Issue tracker facts

- **Templates** (`.github/ISSUE_TEMPLATE/`). `bug.md` auto-applies `type:bug` and asks for the
  Geth version, CL client, OS, commit, expected and actual behaviour, steps and a backtrace.
  `feature.md` auto-applies `type:feature` (Rationale and Implementation). `question.md`
  auto-applies `type:docs` and tells people to ask general questions on Discord or Stack
  Exchange. About 45% of issues skip the templates and arrive with no label.
- **Labels in use**: `type:bug`, `type:feature`, `type:docs`, `status:triage` (maintainer decision
  needed), `need more information`, plus area labels (`rpc`, `snap sync`, `amsterdam`, ...)
  that maintainers set by hand. `slop` marks low-effort AI-generated content and is
  maintainer-only.
- **Agent labels** (sandbox addition, all prefixed `triage:`): `triage:possible-duplicate`,
  `triage:support-question`, `triage:possible-spam`, `triage:security-report`. These are
  suggestions only. `triage-agent:halt` is the maintainer kill switch. The full list with
  colours is `.claude/skills/geth-issue-triage/references/labels.json`.
- **Bot config drift**: `.github/no-response.yml` expects the label `need:more-information`,
  but the label that exists is `need more information`, and `stale.yml` uses
  `status:inactive`, which does not exist. Neither bot acts today, so nothing auto-closes
  issues.
- **Support channels**: Discord `https://discord.gg/nthXNEv`, Ethereum Stack Exchange
  `https://ethereum.stackexchange.com`, docs `https://geth.ethereum.org/docs`.
- **Security**: `SECURITY.md` says vulnerabilities must not be reported in public issues. They
  go to `https://bounty.ethereum.org` or `bounty@ethereum.org`. The Engine API is
  authenticated and trusted, and maintainers decide what counts as a vulnerability.
- **Releases and packages**: GitHub releases, `https://geth.ethereum.org/downloads`, the
  Launchpad PPA `ppa:ethereum/ethereum` (built by `build/ci.go`) and Docker
  `ethereum/client-go`. Missing packages for one distribution are a recurring report.
- **Code owners**: the upstream map of maintainers per directory is preserved in
  `.claude/skills/geth-issue-triage/references/upstream-codeowners.txt`. Never @mention them.
- **Vendored code**: `crypto/bn256/cloudflare` and `crypto/secp256k1/libsecp256k1` are
  upstream copies, so bugs there belong to those projects first.

## Forbidden changes

These rules apply to every agent and contributor tool:

- Do not modify `.github/workflows/**` (including `*.lock.yml`, which only `gh aw compile`
  produces), `AGENTS.md`, `.claude/**`, `CONTRIBUTING.md`, `.github/CODEOWNERS`,
  `SECURITY.md`, `go.mod`, `go.sum` or `build/ci.go` without a maintainer-reviewed pull
  request. `.github/CODEOWNERS` enforces the review.
- Do not add, remove or update dependencies, commit binaries, or force-push.
- The triage agent changes no files at all. It runs read-only, writes only through the
  workflow's safe outputs (labels and one comment on the triggering issue), and must never
  close, lock, assign, transfer or delete issues or merge anything. The workflow grants no
  tool for any of these.
