<?php

/**
 * SPDX-FileCopyrightText: 2016-2024 Nextcloud GmbH and Nextcloud contributors
 * SPDX-FileCopyrightText: 2016 ownCloud, Inc.
 * SPDX-License-Identifier: AGPL-3.0-only
 */

namespace OC\Files\Config;

use OC\Hooks\Emitter;
use OC\Hooks\EmitterTrait;
use OCA\Files_Sharing\MountProvider;
use OCP\Diagnostics\IEventLogger;
use OCP\Files\Config\IHomeMountProvider;
use OCP\Files\Config\IMountProvider;
use OCP\Files\Config\IMountProviderCollection;
use OCP\Files\Config\IPartialMountProvider;
use OCP\Files\Config\IRootMountProvider;
use OCP\Files\Config\IUserMountCache;
use OCP\Files\Config\MountProviderArgs;
use OCP\Files\Mount\IMountManager;
use OCP\Files\Mount\IMountPoint;
use OCP\Files\Storage\IStorageFactory;
use OCP\IUser;
use function get_class;
use function in_array;

class MountProviderCollection implements IMountProviderCollection, Emitter {
	use EmitterTrait;

	/**
	 * @var list<IHomeMountProvider>
	 */
	private array $homeProviders = [];

	/**
	 * @var array<class-string<IMountProvider>, IMountProvider>
	 */
	private array $providers = [];

	/** @var list<IRootMountProvider> */
	private array $rootProviders = [];

	/** @var list<callable> */
	private array $mountFilters = [];

	public function __construct(
		private IStorageFactory $loader,
		private IUserMountCache $mountCache,
		private IEventLogger $eventLogger,
	) {
	}

	/**
	 * @return list<IMountPoint>
	 */
	private function getMountsFromProvider(IMountProvider $provider, IUser $user, IStorageFactory $loader): array {
		$class = str_replace('\\', '_', get_class($provider));
		$uid = $user->getUID();
		$this->eventLogger->start('fs:setup:provider:' . $class, "Getting mounts from $class for $uid");
		$mounts = $provider->getMountsForUser($user, $loader) ?? [];
		$this->eventLogger->end('fs:setup:provider:' . $class);
		return array_values($mounts);
	}

	/**
	 * @param list<IMountProvider> $providers
	 * @return list<IMountPoint>
	 */
	private function getUserMountsForProviders(IUser $user, array $providers): array {
		$loader = $this->loader;
		$mounts = array_map(function (IMountProvider $provider) use ($user, $loader) {
			return $this->getMountsFromProvider($provider, $user, $loader);
		}, $providers);
		$mounts = array_filter($mounts, function ($result) {
			return is_array($result);
		});
		$mounts = array_merge(...$mounts);
		return $this->filterMounts($user, $mounts);
	}

	/**
	 * @return list<IMountPoint>
	 */
	#[\Override]
	public function getMountsForUser(IUser $user): array {
		return $this->getUserMountsForProviders($user, $this->getProviders());
	}

	/**
	 * The caller is responsible to ensure that all provided MountProviderArgs
	 * are for the same user.
	 * And that the `$providerClass` implements IPartialMountProvider.
	 *
	 * @param list<MountProviderArgs> $mountProviderArgs
	 * @return array<string, IMountPoint> IMountPoint array indexed by mount point.
	 */
	public function getUserMountsFromProviderByPath(
		string $providerClass,
		string $path,
		bool $forChildren,
		array $mountProviderArgs,
	): array {
		$providers = $this->getMergedProviders();
		$provider = $providers[$providerClass] ?? null;
		if ($provider === null) {
			return [];
		}
		if (count($mountProviderArgs) === 0) {
			return [];
		}

		if (!$provider instanceof IPartialMountProvider) {
			throw new \LogicException(
				'Mount provider does not support partial mounts'
			);
		}

		$userId = null;
		$user = null;
		foreach ($mountProviderArgs as $mountProviderArg) {
			if ($userId === null) {
				$user = $mountProviderArg->mountInfo->getUser();
				$userId = $user->getUID();
			} elseif ($userId !== $mountProviderArg->mountInfo->getUser()->getUID()) {
				throw new \LogicException('Mounts must belong to the same user!');
			}
		}

		return $provider->getMountsForPath(
			$path,
			$forChildren,
			$mountProviderArgs,
			$this->loader,
		);
	}

	/**
	 * Returns the mounts for the user from the specified provider classes.
	 * Providers not registered in the MountProviderCollection will be skipped.
	 *
	 * @inheritdoc
	 *
	 * @return list<IMountPoint>
	 */
	#[\Override]
	public function getUserMountsForProviderClasses(IUser $user, array $mountProviderClasses): array {
		$providers = array_filter(
			$this->getMergedProviders(),
			fn (string $providerClass) => in_array($providerClass, $mountProviderClasses, true),
			ARRAY_FILTER_USE_KEY
		);
		return $this->getUserMountsForProviders($user, array_values($providers));
	}

	/**
	 * @return list<IMountPoint>
	 */
	public function addMountForUser(IUser $user, IMountManager $mountManager, ?callable $providerFilter = null): array {
		// shared mount provider gets to go last since it needs to know existing files
		// to check for name collisions

		$priorizedMounts = [];
		foreach ($this->providers as $priority => $providers) {
			$priorityMounts = [];
			foreach ($providers as $provider) {
				$mounts = $provider->getMountsForUser($user, $this->loader);
				if (is_array($mounts)) {
					$priorityMounts = array_merge($priorityMounts, $mounts);
				}
			}
			$priorityMounts = $this->filterMounts($user, $priorityMounts);
			$this->eventLogger->start("fs:setup:add-mounts", "Add mounts to the filesystem");
			array_walk($priorityMounts, [$mountManager, 'addMount']);
			$this->eventLogger->end("fs:setup:add-mounts");
			$priorizedMounts[$priority] = $priorityMounts;
		}

		return array_merge(...$priorizedMounts);
	}

	/**
	 * Get the configured home mount for this user
	 *
	 * @since 9.1.0
	 */
	#[\Override]
	public function getHomeMountForUser(IUser $user): IMountPoint {
		$providers = array_reverse($this->homeProviders); // call the latest registered provider first to give apps an opportunity to overwrite builtin
		foreach ($providers as $homeProvider) {
			if ($mount = $homeProvider->getHomeMountForUser($user, $this->loader)) {
				$mount->setMountPoint('/' . $user->getUID()); //make sure the mountpoint is what we expect
				return $mount;
			}
		}
		throw new \Exception('No home storage configured for user ' . $user);
	}

	/**
	 * Add a provider for mount points
	 */
	#[\Override]
	public function registerProvider(IMountProvider $provider, int $priority = self::DEFAULT_PRIORITY): void {
		if ($provider instanceof \OCA\Files_Sharing\MountProvider
			&& $priority === self::DEFAULT_PRIORITY) {
			$priority = self::SHARES_PRIORITY;
		}
		$this->providers[$priority][get_class($provider)] = $provider;
		ksort($this->providers);

		$this->emit('\OC\Files\Config', 'registerMountProvider', [$provider]);
	}

	#[\Override]
	public function registerMountFilter(callable $filter): void {
		$this->mountFilters[] = $filter;
	}

	/**
	 * @param list<IMountPoint> $mountPoints
	 * @return list<IMountPoint>
	 */
	private function filterMounts(IUser $user, array $mountPoints): array {
		return array_values(array_filter($mountPoints, function (IMountPoint $mountPoint) use ($user) {
			foreach ($this->mountFilters as $filter) {
				if ($filter($mountPoint, $user) === false) {
					return false;
				}
			}
			return true;
		}));
	}

	/**
	 * Add a provider for home mount points
	 *
	 * @param IHomeMountProvider $provider
	 * @since 9.1.0
	 */
	#[\Override]
	public function registerHomeProvider(IHomeMountProvider $provider) {
		$this->homeProviders[] = $provider;
		$this->emit('\OC\Files\Config', 'registerHomeMountProvider', [$provider]);
	}

	/**
	 * Get the mount cache which can be used to search for mounts without setting up the filesystem
	 */
	#[\Override]
	public function getMountCache(): IUserMountCache {
		return $this->mountCache;
	}

	public function registerRootProvider(IRootMountProvider $provider): void {
		$this->rootProviders[] = $provider;
	}

	/**
	 * Get all root mountpoints
	 *
	 * @return list<IMountPoint>
	 * @since 20.0.0
	 */
	#[\Override]
	public function getRootMounts(): array {
		$loader = $this->loader;
		$mounts = array_map(function (IRootMountProvider $provider) use ($loader) {
			return $provider->getRootMounts($loader);
		}, $this->rootProviders);
		$mounts = array_reduce($mounts, function (array $mounts, array $providerMounts) {
			return array_merge($mounts, $providerMounts);
		}, []);

		if (count($mounts) === 0) {
			throw new \Exception('No root mounts provided by any provider');
		}

		return array_values($mounts);
	}

	public function clearProviders(): void {
		$this->providers = [];
		$this->homeProviders = [];
		$this->rootProviders = [];
	}

	/*
	 * @return array<string, IMountProvider>
	 */
	private function getMergedProviders(): array
	{
		return array_merge(...$this->providers);
	}

	/**
	 * @return list<IMountProvider>
	 */
	public function getProviders(): array {
		return array_values($this->getMergedProviders());
	}

	/**
	 * @return list<IHomeMountProvider>
	 */
	public function getHomeProviders(): array {
		return $this->homeProviders;
	}

	/**
	 * @return list<IRootMountProvider>
	 */
	public function getRootProviders(): array {
		return $this->rootProviders;
	}
}
