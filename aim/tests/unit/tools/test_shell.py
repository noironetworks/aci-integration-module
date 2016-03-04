#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import traceback

from click import testing
import mock

from aim.tests import base
from aim.tools.cli import shell


class TestShell(base.BaseTestCase):
    """Class for testing AIM """

    def setUp(self):
        super(TestShell, self).setUp()
        self.runner = testing.CliRunner()
        self.invoke = self.runner.invoke

    def run_command(self, command, raises=False):
        result = self.invoke(
            shell.aim,
            ['--config-file', self.test_conf_file] + command.split(' '))
        if raises:
            self._assert_command_exception(result)
        else:
            self._assert_command_no_exception(result)
        return result

    def _assert_command_no_exception(self, result):
        self.assertFalse(
            result.exception,
            "Exception raised by AIM command, output:\n %s \n traceback %s" %
            (result.output,
             '\n'.join(traceback.format_tb(result.exc_info[-1]))))

    def _assert_command_exception(self, result):
        self.assertTrue(
            result.exception, "Exception NOT raised by AIM command, "
                              "output:\n %s" % result.output)

    def _verify_db_manager_params(self, db_manager, num_called=1):
        self.assertTrue(db_manager.called)
        param = db_manager.call_args_list[0][0][0]
        self.assertEqual(3, len(param))
        self.assertTrue(
            param['alembic_repo_path'].endswith(
                'aim/db/migration/alembic_migrations/alembic'))
        self.assertTrue(
            param['alembic_ini_path'].endswith(
                'aim/db/migration/alembic_migrations/alembic.ini'))
        self.assertEqual('sqlite://', param['db_url'])

    def test_aim_db_migration(self):
        # aim db-migration
        result = self.run_command('db-migration')
        self.assertTrue('Usage:' in result.output)

    def test_aim_db_migration_version(self):
        with mock.patch('oslo_db.sqlalchemy.migration_cli.manager'
                        '.MigrationManager') as db_manager:
            instance = db_manager.return_value
            instance.version = mock.Mock()
            # aim db-migration version
            self.run_command(
                'db-migration version')
            self._verify_db_manager_params(db_manager)
            # Manager constructor called
            self.assertTrue(db_manager.called)
            # Version method called
            instance.version.assert_called_with()

    def test_aim_db_migration_upgrade(self):
        with mock.patch('oslo_db.sqlalchemy.migration_cli.manager'
                        '.MigrationManager') as db_manager:
            instance = db_manager.return_value
            instance.upgrade = mock.Mock()
            # aim db-migration upgrade
            self.run_command('db-migration upgrade')
            self._verify_db_manager_params(db_manager)
            # Manager constructor called
            self.assertTrue(db_manager.called)
            # Version method called
            instance.upgrade.assert_called_with('head')

            # test explicit parameter
            instance.upgrade.reset_mock()
            # aim db-migration upgrade rev
            self.run_command('db-migration upgrade rev')
            instance.upgrade.assert_called_with('rev')

    def test_aim_db_migration_stamp(self):
        with mock.patch('oslo_db.sqlalchemy.migration_cli.manager'
                        '.MigrationManager') as db_manager:
            instance = db_manager.return_value
            instance.stamp = mock.Mock()
            # aim db-migration stamp
            self.run_command('db-migration stamp', raises=True)
            self._verify_db_manager_params(db_manager)
            # Raises exception since revision is required
            # Manager constructor called
            self.assertTrue(db_manager.called)

            # test explicit parameter
            # aim db-migration stamp rev
            self.run_command(
                'db-migration stamp rev')
            instance.stamp.assert_called_with('rev')

    def test_aim_db_migration_revision(self):
        with mock.patch('oslo_db.sqlalchemy.migration_cli.manager'
                        '.MigrationManager') as db_manager:
            instance = db_manager.return_value
            instance.revision = mock.Mock()
            # aim db-migration revision
            self.run_command('db-migration revision')
            self._verify_db_manager_params(db_manager)
            # Raises exception since revision is required
            # Manager constructor called
            self.assertTrue(db_manager.called)
            instance.revision.assert_called_with(message='',
                                                 autogenerate=False)

            # test explicit parameter
            instance.revision.reset_mock()
            # aim db-migration revision
            # --message "test message" --no-autogenerate
            self.run_command('db-migration revision '
                             '--message test --autogenerate')
            instance.revision.assert_called_with(message='test',
                                                 autogenerate=True)
