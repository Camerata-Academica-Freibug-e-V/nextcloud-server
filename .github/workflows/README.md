<!--
SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Fork CI

The automatic suite targets `cjh-stable35`, PHP 8.5, MariaDB 12.3.3, and local
primary storage. It runs on pull requests targeting that branch and pushes to
that branch. Each entry-point workflow also supports manual dispatch.

Workflows with a change-detection job skip unrelated checks. Pull requests use
the changed-files API; pushes compare against the pre-push commit, including
multi-commit pushes. Manual dispatch runs the checks without path filtering.
Superseded runs on the same branch are cancelled.

## Retained checks

- PHP syntax, formatting, Rector, Psalm (including taint analysis), and OpenAPI.
- JavaScript/style linting, frontend unit tests, and a production frontend build.
- Autoloader, translation, shipped-file, and licensing checks.
- Database and non-database PHPUnit groups in one PHP 8.5/MariaDB 12.3.3 job.
  Redis remains a test fixture; alternative cache topologies and Memcached are
  not part of this deployment suite.
- Seven Behat suites: capabilities, DAV without S3, general functionality, files
  without large-file tests, file drops, sharees, and sharing. These use MariaDB
  instead of the upstream SQLite installation.
- CalDAV/CardDAV and Litmus tests against PHP 8.5/MariaDB 12.3.3, preserving both
  endpoint variants.
- Login, files, and sharing Playwright tests on two shards. The `sharing` project
  is explicitly included. The installer matrix is excluded.
- CodeQL for Actions and JavaScript/TypeScript, with a weekly scheduled scan.
  There are no daily test schedules.

Playwright still uses the upstream `@nextcloud/e2e-test-server` Docker fixture
and its SQLite database, not the production database/PHP matrix. The fixture
does not expose PHP/image or database selection. Its upstream branch is
`stable35` so external apps are not requested from a fork-only branch.
The PHP version in the Litmus client image is unrelated to the tested server,
which runs PHP 8.5 on the runner.

## Disabled workflows

The original files are preserved in `../disabled-workflows/`, outside GitHub's
workflow discovery directory:

- Upstream release gates, commit-policy checks, AI-policy automation, issue/PR
  administration, and feedback surveys.
- Comment-triggered compilation/submodule updates, automatic dependency
  approval/merging, and automatic Rector/npm changes.
- CA, revocation-list, desktop-version, PR-title, and generated-asset updaters.
- MySQL, PostgreSQL, Oracle, SQLite, 32-bit, sharding, Memcached, alternative
  key-value-store topologies, and separate non-database PHPUnit workflows.
- External/object-storage matrices, S3 primary-storage integration tests, and
  performance benchmarks.

Keep incorporating upstream security and resource updates: disabling the
maintenance bots does not replace CA/revocation-list maintenance.
When restoring a reusable workflow, also restore its caller and review its
versions, triggers, credentials, and upstream-specific assumptions.

## Deployment

These workflows validate changes; they do not deploy or modify the branch.
Build and commit generated assets yourself, or produce them in a separate
deployment build. The frontend build check does not compare the committed
assets with its output.

Deploy only the exact successfully checked commit. Update any branch-protection
rules requiring disabled checks; the Behat summary is now
`integration-mariadb-summary` instead of `integration-sqlite-summary`.
After publishing these changes, re-enable repository Actions if GitHub has
disabled them at repository level.

## Local checks

In a development checkout with initialized submodules, install PHP 8.5 with the
extensions listed in the workflows, Composer, Node 24, and npm 11.3 or later:

```sh
git submodule update --init --recursive
composer install
npm ci
composer run lint
composer run cs:check
composer run psalm
composer run psalm:ocp
composer run psalm:ncu
composer run psalm:strict
composer run psalm:security
npm run lint
npm run stylelint
npm test
npm run build
```

`composer run openapi` regenerates specifications. Autoloader checking also
installs and rewrites generated files; use a clean, disposable checkout.

PHPUnit needs a disposable installed test instance and Redis. Follow the setup
in `phpunit-mariadb.yml`, then run `composer run test:db` and the non-database
test command from that workflow. Never run test-instance setup against live
configuration or data.

For browser tests, start Docker and run:

```sh
npm run playwright:install
BRANCH=stable35 npx playwright test \
  --project=default --project=admin-settings --project=sharing \
  tests/playwright/e2e/login tests/playwright/e2e/files/ \
  tests/playwright/e2e/files_sharing
```

Omit the three test-directory arguments to run all non-installer browser tests.
