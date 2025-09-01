<?php

declare(strict_types=1);

/**
 * SPDX-FileCopyrightText: 2020 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

namespace OCA\DAV\Events;

use OCP\EventDispatcher\Event;

/**
 * Class CachedCalendarObjectCreatedEvent
 *
 * @package OCA\DAV\Events
 * @since 20.0.0
 */
class CachedCalendarObjectCreatedEvent extends Event {

	/**
	 * CachedCalendarObjectCreatedEvent constructor.
	 *
	 * @param int $subscriptionId
	 * @param array $subscriptionData
	 * @param array $shares
	 * @param array $objectData
	 * @param null|string $etag
	 * @since 20.0.0
	 */
	public function __construct(
		private int $subscriptionId,
		private array $subscriptionData,
		private array $shares,
		private array $objectData,
		private ?string $etag,
	) {
		parent::__construct();
	}

	/**
	 * @return int
	 * @since 20.0.0
	 */
	public function getSubscriptionId(): int {
		return $this->subscriptionId;
	}

	/**
	 * @return array
	 * @since 20.0.0
	 */
	public function getSubscriptionData(): array {
		return $this->subscriptionData;
	}

	/**
	 * @return array
	 * @since 20.0.0
	 */
	public function getShares(): array {
		return $this->shares;
	}

	/**
	 * @return array
	 * @since 20.0.0
	 */
	public function getObjectData(): array {
		return $this->objectData;
	}

	/**
	 * @return null|string
     * @since 31.0.0
     */
    public function getEtag(): ?string {
		return $this->etag;
    }

    /**
     * @return void
     * @since 31.0.0
     */
    public function clearEtag(): void {
		$this->etag = null;
    }
}
