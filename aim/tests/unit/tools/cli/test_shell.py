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

import aim
from aim.tests import base
from aim.tools.cli import debug_shell
from aim.tools.cli import shell


class TestShell(base.TestAimDBBase):
    """Class for testing AIM """

    def setUp(self):
        super(TestShell, self).setUp()
        self.runner = testing.CliRunner()
        self.invoke = self.runner.invoke

    def _run_command(self, endpoint, command, raises=False, config_file=None):
        config_file = self.test_conf_file if not config_file else base.etcdir(
            config_file)
        result = self.invoke(
            endpoint,
            ['--config-file', config_file] + command.split(' '))
        if raises:
            self._assert_command_exception(result)
        else:
            self._assert_command_no_exception(result)
        return result

    def run_command(self, command, raises=False, config_file=None):
        return self._run_command(shell.aim, command, raises=raises,
                                 config_file=config_file)

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

    def _verify_db_manager_params(self, db_manager):
        self.assertTrue(db_manager.called)
        param = db_manager.call_args_list[0][0][0]
        self.assertEqual(3, len(param))
        self.assertTrue(
            param['alembic_repo_path'].endswith(
                'aim/db/migration/alembic_migrations'))
        self.assertTrue(
            param['alembic_ini_path'].endswith(
                'aim/db/migration/alembic.ini'))
        self.assertEqual('sqlite://', param['db_url'])


class TestDebugShell(TestShell):

    def run_command(self, command, raises=False, config_file=None):
        return self._run_command(debug_shell.aim_debug, command, raises=raises,
                                 config_file=config_file)


class TestVersion(TestShell):

    def test_version(self):
        result = self.run_command('version')
        self.assertEqual(aim.__version__ + '\n', result.output)
