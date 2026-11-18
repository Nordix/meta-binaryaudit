#!/usr/bin/python3

from binaryaudit.db import wrapper as db_wrapper


class ba_orchestrator:
    '''
    Orchestrator for binaryaudit. The role of this orchestrator is
    to execute the workflow of the abi binary checker.
    '''

    def __init__(self, productname, derivative, build_id, telemetery, logger, db_config="db_config"):
        '''
        '''
        self.logger = logger
        self.productname = productname
        self.derivative = derivative
        self.build_id = build_id
        self.product_id = 0
        self.enable_telemetry = telemetery
        self.db_config = db_config

        # Instantiate the db connection to upload results to DB
        if self.enable_telemetry == 'y':
            self.db_conn = db_wrapper(self.db_config, self.logger)
            self.db_conn.initialize_db()

    def get_product_id(self) -> None:
        '''
        initialize the Product ID based on the entities
        assigns existing Product ID or new Product ID
        '''
        if self.db_conn.is_db_connected:
            self.product_id = self.db_conn.get_product_id(
                    self.productname,
                    self.derivative
            )
            self.logger.note("Product_id: %s" % self.product_id)
        else:
            self.logger.debug("Not connected")

    def perform_binary_audit(self, buildurl, logurl) -> None:
        '''
        inserts product and build id into db
        calls mariner model test and waits for test result
        updates db to record the test result
        '''
        if self.db_conn.is_db_connected:
            self.db_conn.insert_main_transaction(
                    self.build_id,
                    self.product_id,
                    buildurl,
                    logurl
            )
        else:
            self.logger.debug("Not connected")
        # call mariner model
        # wait for test result
        # model = run_command()
        # result = model.popen_output
        # if self.db_conn.is_db_connected:
        #    self.db_conn.update_test_result(
        #             self.build_id,
        #             result
        #     )
        # else:
        #     self.logger.debug("Not connected")
