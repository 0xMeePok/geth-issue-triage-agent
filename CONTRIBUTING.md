# Contributing

Thank you for considering to help out with the source code! We welcome 
contributions from anyone on the internet, and are grateful for even the 
smallest of fixes!

If you'd like to contribute to go-ethereum, please fork, fix, commit and send a 
pull request for the maintainers to review and merge into the main code base. If
you wish to submit more complex changes though, please check up with the core 
devs first on [our gitter channel](https://gitter.im/ethereum/go-ethereum) to 
ensure those changes are in line with the general philosophy of the project 
and/or get some early feedback which can make both your efforts much lighter as
well as our review and merge procedures quick and simple.

## Coding guidelines

Please make sure your contributions adhere to our coding guidelines:

 * Code must adhere to the official Go 
[formatting](https://golang.org/doc/effective_go.html#formatting) guidelines 
(i.e. uses [gofmt](https://golang.org/cmd/gofmt/)).
 * Code must be documented adhering to the official Go 
[commentary](https://golang.org/doc/effective_go.html#commentary) guidelines.
 * Pull requests need to be based on and opened against the `master` branch.
 * Commit messages should be prefixed with the package(s) they modify.
   * E.g. "eth, rpc: make trace configs optional"

## Can I have feature X

Before you submit a feature request, please check and make sure that it isn't 
possible through some other means. The JavaScript-enabled console is a powerful 
feature in the right hands. Please check our 
[Geth documentation page](https://geth.ethereum.org/docs/) for more info
and help.

## Configuration, dependencies, and tests

Please see the [Developers' Guide](https://geth.ethereum.org/docs/developers/geth-developer/dev-guide)
for more details on configuring your environment, managing project dependencies
and testing procedures.

## AI-assisted contributions

This policy applies to every issue, comment and pull request, whether you wrote it yourself
or with an AI tool or agent. It also covers the repository's own triage bot. Rules that can
be enforced mechanically are enforced in the workflow configuration; the rest depend on
maintainer review.

### You are accountable for what you submit

1. **Understand it.** You must be able to explain every line of a PR and every claim in an
   issue. Maintainers may ask you to; unexplained AI output may be closed and labelled `slop`.
2. **Disclose it.** If an AI tool produced a substantial part of an issue or PR, say which tool
   and which parts in the description, e.g. *"AI assistance: the analysis was drafted with an
   LLM; I reproduced the panic myself on v1.17.4."* A `Co-authored-by` trailer for a tool is
   fine, but a human must be the commit author.
3. **Verify it.** Bug reports need evidence you produced yourself: the Geth version, the
   commands or RPC calls you ran, and logs as text. Check findings from AI code scanners
   against current `master` before filing, file one issue per problem, and never file batches
   of generated "audit" reports.
4. **Keep security private.** Never post a suspected vulnerability publicly, however it was
   found. Follow `SECURITY.md` (https://bounty.ethereum.org).
5. **Run the checks.** AI-generated PRs follow the same checklist as everything else
   (`AGENTS.md`): gofmt and goimports, `make all`, `go run ./build/ci.go test`, `lint`, and no
   dependency changes unless the PR is about them.
6. **Agent configuration is code.** Changes to `AGENTS.md`, `.claude/`, `.github/workflows/`
   or this file need a human code-owner review (`.github/CODEOWNERS`). An AI review alone is
   not enough.

### The triage bot

New issues get a first-pass triage from an AI agent (`.github/workflows/issue-triage.md`).

- It can only **add labels** and post **at most one comment** on the issue you opened. It
  cannot close, lock, assign, edit or delete anything, and every decision stays with a
  maintainer. Labels starting with `triage:` are suggestions.
- If it got your issue wrong, reply in the issue. You don't need to do anything else, and a
  maintainer will correct the labels.
- It never asks for secrets, funds, wallet details or "account verification". A comment that
  does is not from the bot, so report it.
- The golden cases were classified by the Cursor agent (model `grok-4.7-xhigh-fast`,
  Grok 4.7 Extra High Fast). The live workflow calls Copilot `gpt-4.1` through Pi. Do not put
  credentials or personal data in issues.
- Maintainers stop the bot by adding the label `triage-agent:halt` to any open issue, or by
  disabling the workflow. Instructions written in an issue cannot stop or steer it.
