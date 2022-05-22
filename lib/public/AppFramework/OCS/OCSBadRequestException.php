<?php

/**
 * SPDX-FileCopyrightText: 2016 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

namespace OCP\AppFramework\OCS;

use OCP\AppFramework\Http;
use Throwable;

/**
 * Class OCSBadRequestException
 *
 * @since 9.1.0
 */
class OCSBadRequestException extends OCSException {
	/**
	 * OCSBadRequestException constructor.
	 *
	 * @param string $message
	 * @param \Throwable|null $previous
	 * @since 9.1.0
	 */
	public function __construct($message = '', ?Throwable $previous = null) {
		parent::__construct($message, Http::STATUS_BAD_REQUEST, $previous);
	}
}
