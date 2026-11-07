<?php

declare(strict_types=1);

/**
 * SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

namespace Test\Files\Config;

use OC\Files\Config\MountProviderCollection;
use OCP\Diagnostics\IEventLogger;
use OCP\Files\Config\IMountProvider;
use OCP\Files\Config\IUserMountCache;
use OCP\Files\Mount\IMountManager;
use OCP\Files\Mount\IMountPoint;
use OCP\Files\Storage\IStorageFactory;
use OCP\IUser;
use PHPUnit\Framework\Attributes\DataProvider;
use Test\TestCase;

class MountProviderCollectionTest extends TestCase {
	public static function providerResults(): array {
		return [[null], [[]]];
	}

	#[DataProvider('providerResults')]
	public function testAddMountForUserPreservesPriorityAndExactResults(?array $emptyMounts): void {
		$loader = $this->createMock(IStorageFactory::class);
		$collection = new MountProviderCollection(
			$loader,
			$this->createMock(IUserMountCache::class),
			$this->createMock(IEventLogger::class),
		);
		$user = $this->createMock(IUser::class);
		$firstMount = $this->createMock(IMountPoint::class);
		$lastMount = $this->createMock(IMountPoint::class);
		$manager = $this->createMock(IMountManager::class);
		$added = [];
		$manager->expects($this->exactly(2))->method('addMount')
			->willReturnCallback(static function (IMountPoint $mount) use (&$added): void {
				$added[] = $mount;
			});

		foreach ([20 => [$lastMount], 10 => [$firstMount], 30 => $emptyMounts] as $priority => $mounts) {
			$provider = $this->createMock(IMountProvider::class);
			$provider->expects($this->once())->method('getMountsForUser')
				->with($user, $loader)
				->willReturnCallback(static function () use ($mounts, $priority, &$added): ?array {
					if ($priority === 20) {
						self::assertCount(1, $added);
					}
					return $mounts;
				});
			$collection->registerProvider($provider, $priority);
		}

		$this->assertSame([$firstMount, $lastMount], $collection->addMountForUser($user, $manager));
		$this->assertSame([$firstMount, $lastMount], $added);
	}
}
