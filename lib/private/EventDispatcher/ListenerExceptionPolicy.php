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
	 * @var WeakMap<Throwable, true>|null
	 */
	private static ?WeakMap $propagating = null;

	public static function mustPropagate(object $event, Throwable $exception): bool {
		self::$propagating ??= new WeakMap();
		$propagate = isset(self::$propagating[$exception])
			|| $exception instanceof AbortedEventException
			|| $event instanceof RestrictInteractionEvent
			|| $event instanceof ValidatePasswordPolicyEvent;
		if ($propagate) {
			self::$propagating[$exception] = true;
		}
		return $propagate;
	}
}
