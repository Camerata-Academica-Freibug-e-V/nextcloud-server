<!--
  - SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
  - SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Copilot Instructions

## Pull request targets

This repository is `Camerata-Academica-Freibug-e-V/nextcloud-server`, a fork of the upstream `nextcloud/server`.

- Never open a pull request against the upstream `nextcloud/server` unless the user explicitly requests it in an interactive session.
- Always target the current default branch of `Camerata-Academica-Freibug-e-V/nextcloud-server`, unless the user explicitly names a different destination.
- Pass the target explicitly, e.g. `gh pr create --repo Camerata-Academica-Freibug-e-V/nextcloud-server --base <default-branch>`; do not rely on the `origin` remote, which points to upstream.
- Base feature branches on the default branch of this repository, not on upstream `master`, so the PR contains only the intended commits.
