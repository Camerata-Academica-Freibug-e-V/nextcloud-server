<?php

declare(strict_types=1);

/**
 * SPDX-FileCopyrightText: 2020 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

namespace OCA\DAV\Events;

use OCP\EventDispatcher\Event;

/**
 * Class CardUpdatedEvent
 *
 * @package OCA\DAV\Events
 * @since 20.0.0
 */
class CardUpdatedEvent extends Event {

	/**
	 * CardUpdatedEvent constructor.
	 *
	 * @param int $addressBookId
	 * @param array $addressBookData
	 * @param array $shares
	 * @param array $cardData
	 * @param null|string $etag
	 * @since 20.0.0
	 */
	public function __construct(
		private int $addressBookId,
		private array $addressBookData,
		private array $shares,
		private array $cardData,
		private ?string $etag,
	) {
		parent::__construct();
	}

	/**
	 * @return int
	 * @since 20.0.0
	 */
	public function getAddressBookId(): int {
		return $this->addressBookId;
	}

	/**
	 * @return array
	 * @since 20.0.0
	 */
	public function getAddressBookData(): array {
		return $this->addressBookData;
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
	public function getCardData(): array {
		return $this->cardData;
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
