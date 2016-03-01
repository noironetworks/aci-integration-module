=================================
AIM CLI developer documentation
=================================

The AIM CLI provides users with useful commands that can range from database migration to model management.

The AIM CLI is based on the third party Click library[0], which provides a easy creation kit for composable command
line interfaces.

The CLI entry point is aim.tools.cli.shell:run, where the main "aim" group is defined.
In order to add a new command, just create a python module with the same as the command in the aim.tools.cli.commands
package, define the command function, add it to the "aim" group using the proper decotator and implement following the
Click documentation on how to add options and parameters [0].

An example of new AIM command is provided in [1].
AIM CLI commands can be unit tested using the proper Click modules, some example tests are already provided in [2]

[0] http://click.pocoo.org
[1] aim/tools/cli/commands/_hello_aim_cli.py
[2] aim/tests/unit/tools/test_shell.py