#!/usr/bin/python3

from sqlalchemy.engine.url import URL
from sqlalchemy import MetaData, create_engine
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
from sqlalchemy import desc
from envparse import env
from datetime import datetime

TRANSACTION_MAIN_RESULT_FAILED = "FAILED"
TRANSACTION_MAIN_RESULT_PASSED = "PASSED"
TRANSACTION_MAIN_RESULT_PENDING = "PENDING"

VERSION_NOT_AVAILABLE = "n/a"


class wrapper:
    '''
    Wrapper class is a database wrapper to wrap all the calls to
    DB. All the application or the modules should use the public
    api of wrapper class
    '''
    def __init__(self, dbconfig, logger) -> None:
        '''
        '''
        self.logger = logger
        self._connection_timeout = 600
        env.read_envfile(dbconfig)

    def _acquire_session(self):
        '''
        '''
        return self._session()

    def _flush_session(self, session) -> None:
        '''
        '''
        session.commit()

    def _release_session(self, session) -> None:
        '''
        '''
        session.close()

    def _initialize_db_connection(self) -> None:
        '''
        '''
        connection_url = URL(
                drivername=env.str('DriverName'),
                host=env.str('Server'),
                database=env.str('Database'),
                username=env.str('User'),
                password=env.str('Password'),
                query={"driver": env.str('Driver')}
        )
        db_engine = create_engine(
                connection_url,
                pool_recycle=self._connection_timeout
        )

        self.logger.note("Initializing database connection")
        metadata = MetaData()
        metadata.reflect(
                db_engine,
                only=[
                    "binaryaudit_checker_baseline_tbl",
                    "binaryaudit_product_tbl",
                    "binaryaudit_abi_checker_transaction_details_tbl",
                    "binaryaudit_transaction_main_tbl"
                ],
        )

        db_map = automap_base(metadata=metadata)
        db_map.prepare()
        self.binaryaudit_checker_baseline_tbl = db_map.classes.binaryaudit_checker_baseline_tbl
        self.binaryaudit_product_tbl = db_map.classes.binaryaudit_product_tbl
        self.binaryaudit_abi_checker_transaction_details_tbl = db_map.classes.binaryaudit_abi_checker_transaction_details_tbl
        self.binaryaudit_transaction_main_tbl = db_map.classes.binaryaudit_transaction_main_tbl

        self._session = sessionmaker(bind=db_engine, expire_on_commit=False)

    def initialize_db(self) -> None:
        '''
        '''
        self._initialize_db_connection()

    def is_db_connected(self) -> bool:
        '''
        checks database connection
        '''
        if self._session:
            return True
        return False

    def get_product_id(self, productname, derivativename) -> int:
        '''
        verifies that the object exists if not, inserts the new object
        and returns the object's Product ID
        '''
        product_id = 0

        session = self._acquire_session()
        record = (
                session.query(
                    self.binaryaudit_product_tbl).filter_by(
                        ProductName=productname,
                        DerivativeName=derivativename
                    ).one_or_none()
        )

        if record is None:
            prd_record = self.binaryaudit_product_tbl(
                    ProductName=productname,
                    DerivativeName=derivativename
            )
            session.add(prd_record)
            self._flush_session(session)

            record = (
                    session.query(
                        self.binaryaudit_product_tbl).filter_by(
                            ProductName=productname,
                            DerivativeName=derivativename
                    ).one_or_none())

        self._release_session(session)
        product_id = record.ProductID

        return product_id

    def insert_main_transaction(self, build_id, product_id, buildurl="", logurl="",
                                result=TRANSACTION_MAIN_RESULT_PENDING, baseline_id=None) -> None:
        '''
        inserts new object to the [main table]
        '''
        session = self._acquire_session()
        date = datetime.utcnow()
        new_tbl_entry = self.binaryaudit_transaction_main_tbl(
                        BuildID=build_id,
                        DateTimeUTC=date,
                        ProductID=product_id,
                        BaselineID=baseline_id,
                        BuildUrl=buildurl,
                        LogUrl=logurl,
                        Result=result
        )
        session.add(new_tbl_entry)
        self._flush_session(session)

    def insert_ba_baseline_data(self, build_id, product_id, pkg_data, date=None) -> None:
        '''
        inserts new object to the [baseline table]
        '''
        if not date:
            date = func.now()
        session = self._acquire_session()
        new_tbl_entry = self.binaryaudit_checker_baseline_tbl(
                        BuildID=build_id,
                        ProductID=product_id,
                        PackageData=pkg_data,
                        DateCreated=date

        )
        session.add(new_tbl_entry)
        self._flush_session(session)

    def insert_ba_transaction_details(self,
                                      build_id,
                                      item_name,
                                      base_version,
                                      new_version,
                                      exec_time,
                                      result,
                                      res_details) -> None:
        '''
        inserts new object to the [details table]
        '''
        session = self._acquire_session()
        date = datetime.utcnow()
        new_tbl_entry = self.binaryaudit_abi_checker_transaction_details_tbl(
                        DateTimeUTC=date,
                        BuildID=build_id,
                        ItemName=item_name,
                        BaseVersion=base_version,
                        NewVersion=new_version,
                        ExecTimeInMicroSec=exec_time,
                        Result=result,
                        ResultDetails=res_details

        )
        session.add(new_tbl_entry)
        self._flush_session(session)

    def update_ba_test_result(self, build_id, result) -> None:
        '''
        locates object with corresponding Build ID in the [main table]
        updates the object's Result entity with test outcome
        '''
        session = self._acquire_session()
        entry = session.query(self.binaryaudit_transaction_main_tbl).get(build_id)
        entry.Result = result
        self._flush_session(session)

    def get_ba_latest_baseline(self, product_id):
        '''
        locates and returns the latest baseline object data
        '''
        session = self._acquire_session()
        record = (
                session.query(
                    self.binaryaudit_checker_baseline_tbl
                ).filter_by(
                    ProductID=product_id,
                ).order_by(desc("DateCreated"))
                .first())
        self._release_session(session)

        return record.ID, record.PackageData
