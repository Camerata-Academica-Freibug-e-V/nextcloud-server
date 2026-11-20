<?php

declare(strict_types=1);
/**
 * SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

namespace OC\AppFramework\Middleware\Security;

use OC\AppFramework\Utility\ControllerMethodReflector;
use OC\Settings\AuthorizedGroupMapper;
use OCP\AppFramework\Http\Attribute\AuthorizedAdminSetting;
use OCP\IUser;

class AuthorizedAdminSettingsAuthorization {
	public function __construct(
		private readonly AuthorizedGroupMapper $mapper,
	) {
	}

	/**
	 * @return list<string>
	 */
	public function getSettingClasses(ControllerMethodReflector $reflector): array {
		$classes = [];
		if ($reflector->hasAnnotation('AuthorizedAdminSetting')) {
			$classes = explode(';', $reflector->getAnnotationParameter('AuthorizedAdminSetting', 'settings'));
		}

		foreach ($reflector->getAttributes(AuthorizedAdminSetting::class) as $attribute) {
			$classes[] = $attribute->newInstance()->getSettings();
		}

		return $classes;
	}

	/**
	 * Checks delegated settings only; callers must enforce other access restrictions.
	 */
	public function isAuthorized(IUser $user, ControllerMethodReflector $reflector): bool {
		$classes = $this->getSettingClasses($reflector);
		$authorizedClasses = $this->mapper->findAllClassesForUser($user);
		foreach ($classes as $class) {
			if (in_array($class, $authorizedClasses, true)) {
				return true;
			}
		}
		return false;
	}
}
