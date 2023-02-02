# Copyright (C) 2023 California Institute of Technology
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""Core workflow functions"""

import os, shutil

from collections.abc import Iterable
from getpass import getuser
from pycondor import Job as pyJob
from pycondor import Dagman as pyDagman

ACCOUNTING_GROUP_USER = os.getenv(
    '_CONDOR_ACCOUNTING_USER',
    getuser(),
)

def makedir(dir_path):
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

def config_override(config, overrides):
    if not overrides:
        return config 
    for ov in overrides:
        split_ov = ov.split(':')
        try:
            ov_sec, ov_key, ov_val = \
                split_ov[0], split_ov[1], ':'.join(split_ov[2:])
        except:
            raise ValueError("Overrides must be in the form 'section:key:value', you used '%s'"%ov)
        if ov_sec not in config.sections():
            config[ov_sec] = {}    
        config[ov_sec][ov_key] = ov_val
    return config

def config_write(config, output_loc):
    with open(output_loc, 'w') as configfile:
        config.write(configfile)


class Job(pyJob):
    """
    Wrapper class of pycondor.Job
    """

    def __init__(self, name, executable, output_arg=None, 
                 output_file=None, accounting_group=None, 
                 extra_lines=[], arguments=None,retry=None,
                 request_disk='2048MB', request_memory='512MB',
                 **kwargs):

        exec_path = shutil.which(executable)
        if exec_path is None:
            raise TypeError('execuatble must be installed in environment'+
                       ' or given as an absolute path')

        if accounting_group is not None:
            condorcmds = [
                "accounting_group = {}".format(accounting_group),
                "accounting_group_user = {}".format(ACCOUNTING_GROUP_USER),
                ]
            condorcmds.extend(extra_lines)
        else:
            raise TypeError('accounting group must be supplied')

        output_args = []
            
        if output_file is not None:
            if isinstance(output_arg, str):
                output_args.append(output_arg)
                if isinstance(output_file, str):
                    self.output_file = [output_file]
                    output_args.append(output_file)
                elif isinstance(output_file, Iterable):
                    self.output_file = output_file
                    for arg in output_file:
                        output_args.append(arg) 
                else:
                    raise TypeError('output_files must be a string or an iterable')
            else:
                raise TypeError('output_arg must be a string')
                
        arguments = ' '.join(list([arguments])+list(output_args))

        if retry == None:
            retry = 3
            
        super(Job,self).__init__(name, exec_path, arguments=arguments,
                                 extra_lines=condorcmds, retry=retry, 
                                 request_disk=request_disk, 
                                 request_memory=request_memory, 
                                 **kwargs)

class Dagman(pyDagman):
    """
    Wrapper class of pycondor.Dagman
    """
    def __init__(self, name, basedir=None, **kwargs):
        self.base_dir = os.path.abspath(basedir)
        self.submit_dir = os.path.join(self.base_dir, 'condor')
        self.error_dir = os.path.join(self.base_dir, 'condor')
        self.log_dir = os.path.join(self.base_dir, 'condor')
        self.output_dir = os.path.join(self.base_dir, 'condor')
        self.result_dir = os.path.join(self.base_dir, 'output')
        super(Dagman,self).__init__(name, submit=self.submit_dir, **kwargs)

    def make_dir(self):
       makedir(self.base_dir)
       makedir(self.submit_dir)
       makedir(self.error_dir)
       makedir(self.log_dir)
       makedir(self.output_dir)
       makedir(self.result_dir)

def collect_job_arguments(config, job_type):
    config_sec = config[job_type]
    args_list = list()
    for key in config_sec.keys():
        args_list.append('--' + str(key))
        val = str(config_sec[key])
        if val[0] == '$':
            val_source = val.replace('${', '').replace('}', '')
            val_source = val_source.split(':')
            val = config[val_source[0]][val_source[1]]
        args_list.append(val)
    return args_list

def create_stochmon_pipe_job(dagman, config, t0=None, tf=None, parents=[], output_path=None):
#pygwb_pipe --param_file parameters.ini --output_path output/ --t0 ${START} --tf ${END}
    dur = int(tf-t0)
    name = f'stochmon_pipe_{int(t0)}_{dur}'
    args = collect_job_arguments(config, 'stochmon_pipe')
    args = args + [
        '--output_path', output_path,
        '--t0', str(t0),
        '--tf', str(tf)
        ]
    job = Job(name=name,
              executable=config['executables']['stochmon_pipe'],
              accounting_group = config['general']['accounting_group'],
              submit=dagman.submit_dir,
              error=dagman.error_dir,
              output=dagman.output_dir,
              log=dagman.log_dir,
              arguments=' '.join(args),
              request_disk='128MB',
              request_memory='2048MB',
              dag=dagman)
    for parent in parents:
        job.add_parent(parent)
    return job

def create_stochmon_combine_job(dagman, config, t0=None, tf=None, parents=[], output_path=None,
    data_path=None, param_file=None,
    alpha=0., fref=30, h0=0.7):
#pygwb_combine --data_path output/ --param_file output/parameters_final.ini --alpha 0 --fref 30 --h0 0.7 --out_path ./output/
    dur = int(tf-t0)
    name = f'stochmon_combine_{int(t0)}_{dur}'
    args = collect_job_arguments(config, 'stochmon_combine')
    args = args + [
        '--param_file', param_file,
        '--out_path', output_path,
        '--data_path', data_path,
        ]
    job = Job(name=name,
              executable=config['executables']['stochmon_combine'],
              accounting_group = config['general']['accounting_group'],
              submit=dagman.submit_dir,
              error=dagman.error_dir,
              output=dagman.output_dir,
              log=dagman.log_dir,
              arguments=' '.join(args),
              request_disk='128MB',
              request_memory='1024MB',
              dag=dagman)
    for parent in parents:
        job.add_parent(parent)
    return job

def create_stochmon_stats_job(dagman, config, t0=None, tf=None, parents=[], output_path=None,
    csd_file=None, dsc_file=None, param_file=None):
#pygwb_stats -c output/point_estimate_sigma_spectra_alpha_0.0_fref_30_${START}-${START}.npz -dsc output/delta_sigma_cut_${START}-${START}.npz -pd output/ -pf output/parameters_final.ini
    dur = int(tf-t0)
    name = f'stochmon_stats_{int(t0)}_{dur}'
    args = collect_job_arguments(config, 'stochmon_stats')
    args = args + [
        '-pf', param_file,
        '-pd', output_path,
        '-c', csd_file,
        '-dsc', dsc_file
        ]
    job = Job(name=name,
              executable=config['executables']['stochmon_stats'],
              accounting_group = config['general']['accounting_group'],
              submit=dagman.submit_dir,
              error=dagman.error_dir,
              output=dagman.output_dir,
              log=dagman.log_dir,
              arguments=' '.join(args),
              request_disk='128MB',
              request_memory='512MB',
              dag=dagman)
    for parent in parents:
        job.add_parent(parent)
    return job

def create_stochmon_html_job(dagman, config, t0=None, tf=None, parents=[], output_path=None, plot_path=None):
#python stochmon_html -p output/ -o output/
    name = f'stochmon_html'
    args = collect_job_arguments(config, 'stochmon_html')
    args = args + [
        '-p', plot_path,
        '-o', output_path,
        ]
    job = Job(name=name,
              executable=config['executables']['stochmon_html'],
              accounting_group = config['general']['accounting_group'],
              submit=dagman.submit_dir,
              error=dagman.error_dir,
              output=dagman.output_dir,
              log=dagman.log_dir,
              arguments=' '.join(args),
              request_disk='128MB',
              request_memory='1024MB',
              dag=dagman)
    for parent in parents:
        job.add_parent(parent)
    return job
