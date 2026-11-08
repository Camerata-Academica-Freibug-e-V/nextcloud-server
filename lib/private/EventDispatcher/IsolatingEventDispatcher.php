<?php

declare(strict_types=1);

/**
 * SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

namespace OC\EventDispatcher;

use Psr\EventDispatcher\StoppableEventInterface;
use Psr\Log\LoggerInterface;
use Symfony\Component\EventDispatcher\EventDispatcher;
use Throwable;

final class IsolatingEventDispatcher extends EventDispatcher {
	public function __construct(
		private LoggerInterface $logger,
	) {
		parent::__construct();
	}

	#[\Override]
	protected function callListeners(iterable $listeners, string $eventName, object $event): void {
		foreach ($listeners as $listener) {
			if ($event instanceof StoppableEventInterface && $event->isPropagationStopped()) {
				break;
			}
			try {
				$listener($event, $eventName, $this);
			} catch (Throwable $exception) {
				if (ListenerExceptionPolicy::mustPropagate($event, $exception)) {
					throw $exception;
				}
				$this->logger->error('Exception in event handler', ['exception' => $exception]);
			}
		}
	}
}
