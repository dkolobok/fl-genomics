import sys
sys.path.append('../utils')

from utils.plink import run_plink

class QC(object):
    """ Class that utilises QC to be used for local QC """
    @staticmethod
    def qc(input_prefix: str, qc_config: dict) -> str:
        """ Runs plink command that performs QC """
        output_prefix = input_prefix + '_filtered'
        run_plink(args_dict={**{'--pfile': input_prefix, # Merging dicts here
                                '--out': output_prefix},
                             **qc_config})
        return output_prefix
