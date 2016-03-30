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

import glob
from os import path

# Commands could be temporary or permanently excluded from the CLI by changing
# their name putting a "_" in front of them. However, to avoid messing up
# the command history too much, the following list can be updated in order
# to void it being loaded.
command_exclude = set([])

modules = glob.glob(path.dirname(__file__) + "/*.py")
# Include all .py files except for those starting with '_'
__all__ = [path.basename(f)[:-3] for f in modules
           if (path.isfile(f) and not path.basename(f)[:-3].startswith('_')
               and path.basename(f)[:-3] not in command_exclude)]
