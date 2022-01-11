<?php

/**
 * SPDX-FileCopyrightText: 2016-2024 Nextcloud GmbH and Nextcloud contributors
 * SPDX-FileCopyrightText: 2016 ownCloud, Inc.
 * SPDX-License-Identifier: AGPL-3.0-only
 */

namespace OC\Files\Config;

use OCP\Files\Mount\IMountPoint;
use OCP\IUser;

class LazyStorageMountInfo extends CachedMountInfo {
	public function __construct(
		IUser $user,
		private IMountPoint $mount,
	) {
		parent::__construct($user, 0, 0, '', '');
		$this->key = '';
	}

	/**
	 * @return int the numeric storage id of the mount
	 */
	#[\Override]
	public function getStorageId(): int {
		if (!$this->storageId) {
			$this->storageId = $this->mount->getNumericStorageId();
		}
		return parent::getStorageId();
	}

	/**
	 * @return int the fileid of the root of the mount
	 */
	#[\Override]
	public function getRootId(): int {
		if (!$this->rootId) {
			$this->rootId = $this->mount->getStorageRootId();
		}
		return parent::getRootId();
	}

	/**
	 * @return string the mount point of the mount for the user
	 */
	#[\Override]
	public function getMountPoint(): string {
		if (!$this->mountPoint) {
			$this->mountPoint = $this->mount->getMountPoint();
		}
		return parent::getMountPoint();
	}

	#[\Override]
	public function getMountId(): ?int {
		return $this->mount->getMountId();
	}

	/**
	 * Get the internal path (within the storage) of the root of the mount
	 *
	 * @return string
	 */
	#[\Override]
	public function getRootInternalPath(): string {
		return $this->mount->getInternalPath($this->mount->getMountPoint());
	}

	#[\Override]
	public function getMountProvider(): string {
		return $this->mount->getMountProvider();
	}

	#[\Override]
	public function getKey(): string {
		if (!$this->key) {
			$this->key = $this->getRootId() . '::' . $this->getMountPoint();
		}
		return $this->key;
	}

	/**
	 * Whether this mount point can be shared with others
	 *
	 * @return bool
	 * @since 24.0.0
	 */
	public function getEnableSharing(): bool {
		return (bool)$this->mount->getOption('enable_sharing', true);
	}

	/**
	 * Whether this mount point needs authentication
	 *
	 * @return bool
	 * @since 24.0.0
	 */
	public function getAuthenticated(): bool {
		return (bool)$this->mount->getOption('authenticated', false);
	}
}
