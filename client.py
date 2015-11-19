#!/usr/bin/env python

import argparse
import logging

import opentuner
from opentuner.measurement import MeasurementDriver
from gce_interface.interface import GCEInterface

log = logging.getLogger(__name__)

parser = argparse.ArgumentParser(add_help = False)
parser.add_argument('--zone',
                    type     = str,
                    default  = "us-central1-f",
                    help     = "The GCE zone.")
parser.add_argument('--project',
                    type     = str,
                    required = True,
                    help     = "The GCE project.")
parser.add_argument('--repo',
                    type     = str,
                    required = True,
                    help     = "The git repository with the tuner.")
parser.add_argument('--interface-path',
                    type     = str,
                    required = True,
                    help     = "The path of your tuner in the repository.")
parser.add_argument('--interface-name',
                    type     = str,
                    required = True,
                    help     = "The name of your measurement interface.")
parser.add_argument('--instances',
                    type     = int,
                    default  = 8,
                    help     = "The number of GCE instances to create.")

class MeasurementClient(MeasurementDriver):
    def __init__(self,
                 measurement_interface,
                 input_manager,
                 **kwargs):
        super(MeasurementClient, self).__init__(measurement_interface,
                                                input_manager,
                                                **kwargs)

        self.gce_interface = GCEInterface(zone            = self.args.zone,
                                          project         = self.args.project,
                                          repo            = self.args.repo,
                                          interface_path  = self.args.interface_path,
                                          interface_name  = self.args.interface_name,
                                          instance_number = self.args.instances)

        self.gce_interface.create_and_connect_all()

    def process_all(self):
        self.lap_timer()
        q = self.query_pending_desired_results()
        desired_results = []

        for dr in q.all():
          if self.claim_desired_result(dr):
            desired_results.append(dr)

        self.run_desired_results(desired_results)

    def run_desired_results(self, desired_results):
        requests_info = []

        for desired_result in desired_results:
            desired_result.limit = self.run_time_limit(desired_result)

            input = self.input_manager.select_input(desired_result)
            self.session.add(input)
            self.session.flush()

            log.debug('running desired result %s on input %s', desired_result.id,
                      input.id)

            self.input_manager.before_run(desired_result, input)

            requests_info.append((desired_result.configuration,
                                  input,
                                  desired_result.limit))

        requests  = self.gce_interface.request_results(requests_info)
        results   = []

        requested = len(requests)
        i         = 0

        while len(results) < requested:
            request = requests[i]
            result  = self.gce_interface.query_result(request)

            if result != None:
                d_result = desired_results[request[2]]
                input    = requests_info[request[2]][1]

                results.append((result, input, i))
                requests.pop(i)

                self.report_result(d_result, result, input)

            i += 1

            if i == len(requests):
                i = 0
