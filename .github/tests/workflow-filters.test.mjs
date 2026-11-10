/*
 * SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { matchesGlob } from 'node:path'
import { test } from 'node:test'

const workflows = new URL('../workflows/', import.meta.url)
const phpChecks = [
	'lint-php.yml', 'lint-php-cs.yml', 'rector.yml', 'static-code-analysis.yml',
	'phpunit.yml', 'integration-mariadb.yml', 'integration-dav.yml',
	'integration-litmus.yml', 'autocheckers.yml', 'openapi.yml',
]
const frontendChecks = ['lint-eslint.yml', 'node-test.yml', 'npm-build.yml']
const filteredChecks = [...phpChecks, ...frontendChecks, 'lint-stylelint.yml', 'playwright.yml']

function filters(name) {
	const source = readFileSync(new URL(name, workflows), 'utf8')
	const block = source.split('          filters: |\n')[1]
	assert.ok(block, `${name}: missing path filters`)
	const result = {}
	let group
	// These workflow filters use only named lists of single-quoted globs.
	for (const line of block.split('\n')) {
		if (/^ {0,10}\S/.test(line)) {
			break
		}
		if (!line.trim()) {
			continue
		}
		const key = line.match(/^ {12}(\w+):$/)
		if (key) {
			group = key[1]
			result[group] = []
			continue
		}
		const pattern = line.match(/^ {14}- '([^']+)'$/)
		assert.ok(pattern && group, `${name}: unsupported filter entry: ${line}`)
		result[group].push(pattern[1])
	}
	return result
}

function selects(name, path, group = 'src') {
	const patterns = filters(name)[group]
	assert.ok(patterns, `${name}: missing ${group} filter`)
	return patterns.some((pattern) => matchesGlob(path, pattern))
}

test('workflow YAML changes select their consumers, not unrelated application suites', () => {
	for (const changed of filteredChecks) {
		for (const workflow of filteredChecks) {
			assert.equal(
				selects(workflow, `.github/workflows/${changed}`),
				workflow === changed,
				`${changed} -> ${workflow}`,
			)
		}
		assert.ok(selects('tooling.yml', `.github/workflows/${changed}`, 'tools'))
	}
	assert.ok(selects('phpunit.yml', '.github/workflows/phpunit-mariadb.yml'))
	for (const workflow of filteredChecks) {
		assert.equal(selects(workflow, '.github/workflows/README.md'), false, workflow)
	}
})

test('PHP changes and Composer dependencies preserve backend regression checks', () => {
	for (const workflow of phpChecks) {
		for (const file of [
			'lib/private/Files/Cache/Cache.php',
			'apps/files_sharing/tests/ControllerTest.php',
			'composer.json', 'vendor-bin/phpunit/composer.lock',
		]) {
			assert.ok(selects(workflow, file), `${file} -> ${workflow}`)
		}
		assert.equal(selects(workflow, 'tests/playwright/e2e/files/example.spec.ts'), false, workflow)
	}
})

test('frontend sources and nested manifests select frontend checks but not PHP suites', () => {
	for (const file of [
		'apps/files/src/views/Files.vue', 'core/src/test.spec.ts',
		'build/frontend/package.json', 'build/frontend-legacy/package-lock.json',
	]) {
		for (const workflow of frontendChecks) {
			assert.ok(selects(workflow, file), `${file} -> ${workflow}`)
		}
		for (const workflow of phpChecks) {
			assert.equal(selects(workflow, file), false, `${file} -> ${workflow}`)
		}
	}
	assert.ok(selects('lint-stylelint.yml', 'core/css/server.scss'))
	assert.ok(selects('lint-stylelint.yml', 'stylelint.config.js'))
	assert.equal(selects('lint-stylelint.yml', 'apps/files/src/test.spec.ts'), false)
})

test('root and build tooling changes do not fan out into application suites', () => {
	for (const file of [
		'build/update-configured-apps.sh', 'helper.py', 'Makefile',
		'build/pack-apps.sh', 'build/pack-support-app.py',
		'build/integration/install-dependencies.py',
		'build/integration/tests/test_install_dependencies.py',
		'build/tests/test-pack-apps.py', 'build/frontend/helper.py',
		'build/frontend-legacy/helper.sh', 'tests/test_update_apps.py',
	]) {
		for (const workflow of filteredChecks) {
			assert.equal(selects(workflow, file), false, `${file} -> ${workflow}`)
		}
		assert.ok(selects('tooling.yml', file, 'tools'), file)
	}
})

test('script consumers retain directly related checks without unrelated suites', () => {
	const consumers = {
		'build/demi.sh': ['npm-build.yml'],
		'build/npm-post-build.sh': ['npm-build.yml'],
		'build/integration/run.sh': ['integration-mariadb.yml'],
		'build/openapi-checker.sh': ['openapi.yml'],
	}
	for (const [file, expected] of Object.entries(consumers)) {
		for (const workflow of filteredChecks) {
			assert.equal(selects(workflow, file), expected.includes(workflow), `${file} -> ${workflow}`)
		}
	}
	assert.ok(selects('autocheckers.yml', 'build/autoloaderchecker.sh', 'autoloader'))
	assert.ok(selects('autocheckers.yml', 'build/psalm-checker.sh', 'psalm'))
	assert.equal(selects('autocheckers.yml', 'build/autoloaderchecker.sh', 'src'), false)
	assert.equal(selects('autocheckers.yml', 'build/psalm-checker.sh', 'src'), false)
})

test('test fixtures select their own suites', () => {
	assert.ok(selects('integration-mariadb.yml', 'build/integration/features/auth.feature'))
	assert.ok(selects('integration-mariadb.yml', 'build/integration/config/behat.yml'))
	assert.ok(selects('phpunit.yml', 'tests/phpunit-autotest.xml'))
	assert.ok(selects('phpunit.yml', 'tests/data/example.json'))
	assert.ok(selects('phpunit.yml', 'apps/dav/tests/unit/test_fixtures/calendar.ics'))
	assert.equal(selects('node-test.yml', 'apps/dav/tests/unit/test_fixtures/example.json'), false)
	assert.ok(selects('integration-dav.yml', 'apps/dav/tests/testsuits/caldavtest/CalDAV/sync-report.xml'))
	assert.ok(selects('playwright.yml', 'tests/playwright/support/sections/FilesPage.ts'))
	assert.ok(selects('node-test.yml', 'apps/files/src/__tests__/__snapshots__/test.snap'))
	assert.ok(selects('npm-build.yml', 'build/frontend-legacy/patches/example.patch'))
})

test('Composer fixture prerequisites are selected only for dependency tests or all-tool runs', () => {
	for (const file of [
		'build/integration/install-dependencies.py',
		'build/integration/tests/test_install_dependencies.py',
		'build/run-tool-tests.py', '.github/workflows/tooling.yml',
	]) {
		assert.ok(selects('tooling.yml', file, 'composer'), file)
	}
	for (const file of ['Makefile', 'build/pack-apps.sh', '.github/workflows/phpunit.yml']) {
		assert.equal(selects('tooling.yml', file, 'composer'), false, file)
	}
})
