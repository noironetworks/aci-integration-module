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
from oslo_db import options as db_options
try:
    from oslo_db.sqlalchemy import session as db_session
except ImportError:  # oslo.db without legacy session facade support
    db_session = None
from oslo_db.sqlalchemy import enginefacade

from aim import aim_store

cfg.CONF.register_opts(db_options.database_opts, group='database')

_FACADE = None
_ENGINE = None
_SESSIONMAKER = None
_LEGACY_ENGINE_FACADE = getattr(db_session, 'EngineFacade', None)


def _configure():
    global _FACADE, _ENGINE, _SESSIONMAKER

    if _FACADE is not None:
        return

    if _LEGACY_ENGINE_FACADE is not None:
        _FACADE = _LEGACY_ENGINE_FACADE.from_config(
            cfg.CONF, sqlite_fk=True)
        return

    _FACADE = enginefacade.transaction_context()
    _FACADE.configure(sqlite_fk=True)

    _ENGINE = _FACADE.writer.get_engine()
    _SESSIONMAKER = _FACADE.writer.get_sessionmaker()


def get_engine():
    """Helper method to grab engine."""
    _configure()
    if _ENGINE is not None:
        return _ENGINE
    return _FACADE.get_engine()


def dispose():
    # Don't need to do anything if an enginefacade hasn't been created
    if _ENGINE is not None:
        _ENGINE.pool.dispose()
    elif _FACADE is not None:
        _FACADE.get_engine().pool.dispose()


def get_session(autocommit=True, expire_on_commit=True, use_slave=False):
    """Helper method to grab session."""
    _configure()
    if _SESSIONMAKER is not None:
        # The newer transaction_context path does not expose use_slave/
        # autocommit controls.
        return _SESSIONMAKER(expire_on_commit=expire_on_commit)
    try:
        return _FACADE.get_session(autocommit=autocommit,
                                   expire_on_commit=expire_on_commit,
                                   use_slave=use_slave)
    except TypeError:
        # Some legacy facade/version combinations may not support
        # autocommit in the signature.
        return _FACADE.get_session(expire_on_commit=expire_on_commit,
                                   use_slave=use_slave)


def get_store(autocommit=True, expire_on_commit=True, use_slave=False):
    store = cfg.CONF.aim.aim_store

    if store == 'sql':
        db_session = get_session(
            autocommit=autocommit,
            expire_on_commit=expire_on_commit,
            use_slave=use_slave)
        return aim_store.SqlAlchemyStore(db_session)

    elif store == 'k8s':
        return aim_store.K8sStore(
            namespace=cfg.CONF.aim_k8s.k8s_namespace,
            config_file=cfg.CONF.aim_k8s.k8s_config_path,
            vmm_domain=cfg.CONF.aim_k8s.k8s_vmm_domain,
            vmm_controller=cfg.CONF.aim_k8s.k8s_controller)
