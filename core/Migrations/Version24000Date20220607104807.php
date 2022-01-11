<?php

declare(strict_types=1);

namespace OC\Core\Migrations;

use Closure;
use OCP\DB\ISchemaWrapper;
use OCP\DB\Types;
use OCP\Migration\IOutput;
use OCP\Migration\SimpleMigrationStep;

/**
 * Auto-generated migration step: Please modify to your needs!
 */
class Version24000Date20220607104807 extends SimpleMigrationStep {

	/**
	 * @param IOutput $output
	 * @param Closure $schemaClosure The `\Closure` returns a `ISchemaWrapper`
	 * @param array $options
	 * @return null|ISchemaWrapper
	 */
	public function changeSchema(IOutput $output, Closure $schemaClosure, array $options): ?ISchemaWrapper {
		/** @var ISchemaWrapper $schema */
		$schema = $schemaClosure();

		$table = $schema->getTable('mounts');
		$changed = false;
		if (!$table->hasColumn('enable_sharing')) {
			$table->addColumn('enable_sharing', Types::SMALLINT, [
				'default' => 1,
			]);
			$table->addIndex(['enable_sharing'], 'mounts_enable_sharing');
			$changed = true;
		}
		if (!$table->hasColumn('authenticated')) {
			$table->addColumn('authenticated', Types::SMALLINT, [
				'default' => 0,
			]);
			$table->addIndex(['authenticated'], 'mounts_authenticated');
			$changed = true;
		}
		return $changed ? $schema : null;
	}
}
