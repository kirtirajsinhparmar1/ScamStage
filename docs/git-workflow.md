# Git workflow

`main` is the stable demo; `dev` is the tested integration branch.
Feature branches merge by pull request into `dev`; tested `dev` merges by PR into `main`.

The local repository starts with a shared bootstrap commit on main/dev and the backend
foundation on `feat/backend-foundation`. There is no remote configured yet.

## Publish to a new empty GitHub repository

Create an empty `scamstage` repository in your GitHub account (do not add a README there).
Replace the placeholder URL below with that repository's actual URL:

```sh
git remote add origin <your-repository-url>
git push -u origin main
git push -u origin dev
git push -u origin feat/backend-foundation
```

These initial main/dev pushes publish the bootstrap only. Open a pull request from
`feat/backend-foundation` into `dev`; let Backend checks pass and review before merging.
If the remote already contains work, clone and reconcile it instead of force-pushing.
No GitHub repository has been created or pushed by this setup.

After the initial push, configure GitHub branch rules for main/dev: require a PR,
one teammate approval, and the backend CI check. Local branches alone do not enforce these rules.

## Daily Person 2 workflow

After the foundation PR merges:

```sh
git switch dev
git pull --ff-only origin dev
git switch -c feat/backend-sessions
# Make the change, then:
make check
git add services/api packages/contracts docs/handoffs
git commit -m "feat(api): add session lifecycle"
git push -u origin feat/backend-sessions
```

Open a PR into `dev`. Review the diff before committing and include any other intentionally
changed files, such as dependency manifests and uv.lock. Do not commit `.env`.

Person 1 uses `feat/frontend-call-interface`; Person 3 uses `feat/nemotron-adapter`.
Each starts from current dev and documents what's usable, checks run and remaining stubs.
Person 2 owns integration and promotes a verified checkpoint from dev to main by PR.

## Commit identity

No Git author was configured on this machine. The initial setup commits use
`Codex <codex@localhost>` through command-scoped settings; global Git settings were not changed.
Before your own commits, set your identity locally:

```sh
git config user.name "Your Name"
git config user.email "your GitHub email"
```
