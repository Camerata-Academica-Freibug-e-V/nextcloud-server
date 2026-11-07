<?php

declare(strict_types=1);

/**
 * SPDX-FileCopyrightText: 2024 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

namespace OCA\DAV\CalDAV;

use DateTime;
use DateTimeInterface;
use Sabre\VObject\DateTimeParser;

class EventReaderRDate extends \Sabre\VObject\Recur\RDateIterator {

	public function concludes(): ?DateTime {
		return $this->concludesOn();
	}

	public function concludesAfter(): ?int {
		return !empty($this->dates) ? count($this->dates) : null;
	}

	public function concludesOn(): ?DateTime {
		$lastDate = null;
		foreach ($this->dates as $date) {
			$date = $date instanceof DateTimeInterface
				? DateTime::createFromInterface($date)
				: DateTime::createFromInterface(DateTimeParser::parse($date, $this->startDate->getTimezone()));
			if ($lastDate === null || $date > $lastDate) {
				$lastDate = $date;
			}
		}
		return $lastDate;
	}

}
