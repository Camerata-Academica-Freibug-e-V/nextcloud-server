<?php

declare(strict_types=1);

/**
 * SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

namespace Test\Preview;

use OC\Preview\SVG;
use Test\TestCase;

class SVGCanBeProcessedTest extends TestCase {
	#[\PHPUnit\Framework\Attributes\TestWith(['image.svg', false])]
	#[\PHPUnit\Framework\Attributes\TestWith(['', false])]
	#[\PHPUnit\Framework\Attributes\TestWith(['#local', true])]
	public function testXlinkHref(string $href, bool $expected): void {
		$provider = new class extends SVG {
			public function canProcess(string $content): bool {
				return $this->canBeProcessed($content);
			}
		};

		self::assertSame($expected, $provider->canProcess('<svg xmlns:xlink="http://www.w3.org/1999/xlink"><image xlink:href="' . $href . '"/></svg>'));
	}
}
