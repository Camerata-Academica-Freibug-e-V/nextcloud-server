<?php

declare(strict_types=1);

/**
 * SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

namespace OC\EventDispatcher;

use OCP\Exceptions\AbortedEventException;
use OCP\Interaction\RestrictInteractionEvent;
use OCP\Security\Events\ValidatePasswordPolicyEvent;
use Throwable;
use WeakMap;

final class ListenerExceptionPolicy {
	/**
	 * Keep nested validation failures propagating through enclosing notification listeners.
	 * @var WeakMap<Throwable, true>
	 */
	private WeakMap $propagating;

	public function __construct() {
		$this->propagating = new WeakMap();
	}

	public function mustPropagate(object $event, Throwable $exception): bool {
		$propagate = isset($this->propagating[$exception])
			|| $exception instanceof AbortedEventException
			|| $event instanceof RestrictInteractionEvent
			|| $event instanceof ValidatePasswordPolicyEvent;
		if ($propagate) {
			$this->propagating[$exception] = true;
		}
		return $propagate;
	}
}
