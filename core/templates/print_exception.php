<?php

declare(strict_types=1);

use OCP\IL10N;

/**
 * SPDX-FileCopyrightText: 2016-2024 Nextcloud GmbH and Nextcloud contributors
 * SPDX-FileCopyrightText: 2012-2015 ownCloud, Inc.
 * SPDX-License-Identifier: AGPL-3.0-only
 */

function print_exception(Throwable $e, IL10N $l): void {
	print_unescaped('<h3>');
	p($l->t('Details'));
	print_unescaped('</h3>');
	print_unescaped('<ul><li>');
	p($l->t('Type: %s', [get_class($e)]));
	print_unescaped('</li><li>');
	p($l->t('Code: %s', [$e->getCode()]));
	print_unescaped('</li><li>');
	p($l->t('Message: %s', [$e->getMessage()]));
	print_unescaped('</li><li>');
	p($l->t('File: %s', [$e->getFile()]));
	print_unescaped('</li><li>');
	p($l->t('Line: %s', [$e->getLine()]));
	print_unescaped('</li></ul>');
	print_unescaped('<br />');
	print_unescaped('<h3>');
	p($l->t('Trace'));
	print_unescaped('</h3>');
	print_unescaped('<pre>');
	p($e->getTraceAsString());
	print_unescaped('</pre>');

	if ($e->getPrevious() !== null) {
		print_unescaped('<br />');
		print_unescaped('<h4>');
		p($l->t('Previous'));
		print_unescaped('</h4>');

		print_exception($e->getPrevious(), $l);
	}
}
