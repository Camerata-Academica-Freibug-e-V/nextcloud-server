<?php

declare(strict_types=1);

/**
 * SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

namespace Test\Files\Cache;

use OC\DB\QueryBuilder\Partitioned\PartitionedQueryBuilder;
use OC\DB\QueryBuilder\Partitioned\PartitionSplit;
use OC\DB\QueryBuilder\Sharded\AutoIncrementHandler;
use OC\DB\QueryBuilder\Sharded\ShardConnectionManager;
use OC\Files\Cache\Storage;
use OC\Files\Cache\StorageGlobal;
use OCP\DB\QueryBuilder\IQueryBuilder;
use OCP\IDBConnection;
use OCP\Server;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Group;
use Test\TestCase;

#[Group('DB')]
class StorageGlobalTest extends TestCase {
	private IDBConnection $connection;
	private string $storageId;
	private int $numericId;
	private int $rootId;

	#[\Override]
	protected function setUp(): void {
		parent::setUp();
		$this->connection = Server::get(IDBConnection::class);
		$this->storageId = $this->getUniqueID('storage-global-');

		$query = $this->connection->getQueryBuilder();
		$query->insert('storages')->values([
			'id' => $query->createNamedParameter($this->storageId),
			'available' => $query->createNamedParameter(1, IQueryBuilder::PARAM_INT),
			'last_checked' => $query->createNamedParameter(123, IQueryBuilder::PARAM_INT),
		])->executeStatement();
		$this->numericId = (int)$query->getLastInsertId();

		$query = $this->connection->getQueryBuilder();
		$query->insert('filecache')->values([
			'storage' => $query->createNamedParameter($this->numericId, IQueryBuilder::PARAM_INT),
			'path' => $query->createNamedParameter(''),
			'path_hash' => $query->createNamedParameter(md5('')),
		])->executeStatement();
		$this->rootId = (int)$query->getLastInsertId();
	}

	#[\Override]
	protected function tearDown(): void {
		$query = $this->connection->getQueryBuilder();
		$query->delete('filecache')
			->where($query->expr()->eq('storage', $query->createNamedParameter($this->numericId, IQueryBuilder::PARAM_INT)))
			->executeStatement();
		$query = $this->connection->getQueryBuilder();
		$query->delete('storages')
			->where($query->expr()->eq('numeric_id', $query->createNamedParameter($this->numericId, IQueryBuilder::PARAM_INT)))
			->executeStatement();
		parent::tearDown();
	}

	public static function lookupModes(): array {
		return [
			'storage IDs' => [false, false],
			'numeric IDs' => [true, false],
			'partitioned storage IDs' => [false, true],
			'partitioned numeric IDs' => [true, true],
		];
	}

	private function createCache(bool $partitioned): StorageGlobal {
		$connection = $this->createMock(IDBConnection::class);
		$connection->method('getQueryBuilder')->willReturnCallback(function () use ($partitioned): IQueryBuilder {
			$query = $this->connection->getQueryBuilder();
			if ($partitioned && !$query instanceof PartitionedQueryBuilder) {
				$query = new PartitionedQueryBuilder(
					$query,
					[],
					Server::get(ShardConnectionManager::class),
					Server::get(AutoIncrementHandler::class),
				);
				$query->addPartition(new PartitionSplit('filecache', ['filecache']));
			}
			return $query;
		});
		return new StorageGlobal($connection);
	}

	#[DataProvider('lookupModes')]
	public function testStorageInfoAndCacheInvalidation(bool $numeric, bool $partitioned): void {
		$cache = $this->createCache($partitioned);
		if ($numeric) {
			$cache->loadForNumericIds([$this->numericId]);
		} else {
			$cache->loadForStorageIds([$this->storageId]);
		}
		$expected = [
			'id' => $this->storageId,
			'numeric_id' => $this->numericId,
			'available' => true,
			'last_checked' => 123,
			'fileid' => $this->rootId,
		];
		$this->assertSame($expected, $cache->getStorageInfo($this->storageId));
		$this->assertSame($expected, $cache->getStorageInfoByNumericId($this->numericId));
		$this->assertSame($this->storageId, $cache->getStorageId($this->numericId));

		$query = $this->connection->getQueryBuilder();
		$query->update('storages')
			->set('last_checked', $query->createNamedParameter(456, IQueryBuilder::PARAM_INT))
			->where($query->expr()->eq('numeric_id', $query->createNamedParameter($this->numericId, IQueryBuilder::PARAM_INT)))
			->executeStatement();
		$this->assertSame($expected, $cache->getStorageInfoByNumericId($this->numericId));
		$cache->clearCache();
		$expected['last_checked'] = 456;
		$this->assertSame($expected, $cache->getStorageInfoByNumericId($this->numericId));
		$this->assertSame($expected, $cache->getStorageInfo($this->storageId));
	}

	#[DataProvider('lookupModes')]
	public function testStorageWithoutRoot(bool $numeric, bool $partitioned): void {
		$query = $this->connection->getQueryBuilder();
		$query->delete('filecache')
			->where($query->expr()->eq('storage', $query->createNamedParameter($this->numericId, IQueryBuilder::PARAM_INT)))
			->executeStatement();
		$cache = $this->createCache($partitioned);
		$info = $numeric ? $cache->getStorageInfoByNumericId($this->numericId) : $cache->getStorageInfo($this->storageId);
		$this->assertNotNull($info);
		$this->assertNull($info['fileid']);
		$this->assertSame($this->storageId, $cache->getStorageId($this->numericId));
	}

	public function testUnknownStorage(): void {
		$cache = $this->createCache(false);
		$this->assertNull($cache->getStorageInfo($this->storageId . '-missing'));
		$this->assertNull($cache->getStorageInfoByNumericId(-1));
		$this->assertNull($cache->getStorageId(-1));
	}

	public function testLongStorageId(): void {
		$storageId = str_repeat($this->storageId, 20);
		$query = $this->connection->getQueryBuilder();
		$query->update('storages')
			->set('id', $query->createNamedParameter(Storage::adjustStorageId($storageId)))
			->where($query->expr()->eq('numeric_id', $query->createNamedParameter($this->numericId, IQueryBuilder::PARAM_INT)))
			->executeStatement();
		$cache = $this->createCache(false);
		$cache->loadForStorageIds([$storageId]);
		$this->assertSame($this->rootId, $cache->getStorageInfo($storageId)['fileid']);
		$this->assertSame(Storage::adjustStorageId($storageId), $cache->getStorageId($this->numericId));
	}
}
