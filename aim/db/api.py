# Copyright (c) 2016 Cisco Systems
# All Rights Reserved.
#
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

from oslo_config import cfg
from oslo_db.sqlalchemy import session

from aim import aim_store


_FACADE = None


def _create_facade_lazily():
    global _FACADE

    if _FACADE is None:
        _FACADE = session.EngineFacade.from_config(cfg.CONF, sqlite_fk=True)

    return _FACADE


def get_engine():
    """Helper method to grab engine."""
    facade = _create_facade_lazily()
    return facade.get_engine()


def dispose():
    # Don't need to do anything if an enginefacade hasn't been created
    if _FACADE is not None:
        get_engine().pool.dispose()


def get_session(autocommit=True, expire_on_commit=True, use_slave=False):
    """Helper method to grab session."""
    facade = _create_facade_lazily()
    return facade.get_session(autocommit=autocommit,
                              expire_on_commit=expire_on_commit,
                              use_slave=use_slave)


def get_store(autocommit=True, expire_on_commit=True, use_slave=False):
    store = cfg.CONF.aim.aim_store
    if store == 'sql':
        db_session = get_session(
            autocommit=autocommit, expire_on_commit=expire_on_commit,
            use_slave=use_slave)
        return aim_store.SqlAlchemyStore(db_session)
    elif store == 'k8s':
        return aim_store.K8sStore(cfg.CONF.aim_k8s.k8s_namespace,
                                  cfg.CONF.aim_k8s.k8s_config_path)
