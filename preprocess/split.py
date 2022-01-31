from abc import abstractmethod
from ukb_loader import UKBDataLoader
from numpy.random import seed, choice
import pandas as pd

import sys
sys.path.append('../config')

from config.path import data_root, valid_ids_path, ukb_loader_dir, ukb_bfile_path
from utils.plink import run_plink

class SplitBase(object):
    def __init__(self, split_config: dict):
        self.split_config = split_config

    @abstractmethod
    def split(self):
        pass
    
    def split_by_ethnicity(self) -> pd.DataFrame:
        loader = UKBDataLoader(ukb_loader_dir, 'split', '21000', ['31'])
        df = pd.concat((loader.load_train(), loader.load_val(), loader.load_test()))
        df.columns = ['sex', 'ethnic_background']

        # Include FID/IID fields for plink to play nice with the output files
        df['FID'] = df.index
        df['IID'] = df.index
        # Leave only those samples that passed population QC
        pop_qc_ids = pd.read_csv(valid_ids_path, index_col='IID')
        df = df.loc[df.index.intersection(pop_qc_ids.index)]

        df.ethnic_background[df.ethnic_background.isna()] = 0.0
        df.ethnic_background = df.ethnic_background.astype('int')
        # Drop samples with missing/prefer not to answer ethnic background
        df = df[~df.ethnic_background.isin([-1, -3, 0])]
        # Map ethnic backgrounds to our defined splits
        df['split_code'] = df.ethnic_background.map(self.split_config['split_map'])
        
        return df
    
    def make_split_pgen(self, split_id_path: str, prefix: str) -> None:
        run_plink(args_dict={'--bfile': ukb_bfile_path,
                             '--out': prefix,
                             '--keep': split_id_path},
                  args_list=['--make-pgen'])

    
class SplitIID(SplitBase):
    def split(self, make_pgen=True):
        df = self.split_by_ethnicity()
        df = df.loc[df.split_code == 0]
        
        seed(32)
        df['split'] = choice(list(range(self.split_config['n_iid_splits'])), size=df.shape[0], replace=True)
        
        prefix_list = []        
        for i in range(self.split_config['n_iid_splits']):
            split_id_path = f"{data_root}/{self.split_config['iid_split_name']}/split_ids/{i}.csv"
            prefix = f"{data_root}/{self.split_config['iid_split_name']}/genotypes/split_{i}"
            prefix_list.append(prefix)
            df.loc[(df.split == i), ['FID', 'IID', 'sex']].to_csv(split_id_path, index=False, sep='\t')
            
            if make_pgen:
                self.make_split_pgen(split_id_path, prefix)
            
        return prefix_list
        
        
class SplitNonIID(SplitBase):
    def split(self, make_pgen=True):
        df = self.split_by_ethnicity()
        seed(32)
        holdout_idx = choice(df.index, size=int(df.shape[0]*self.split_config['non_iid_holdout_ratio']), replace=False)
        df['split']= None
        df.loc[holdout_idx, 'split'] = 5
                        
        for i in range(5):
            df.loc[(df.split_code == i) & (df.split != 5), 'split'] = i
        
        prefix_list = []
        for i in range(6):
            split_id_path = f"{data_root}/{self.split_config['non_iid_split_name']}/split_ids/{i}.csv"
            prefix = f"{data_root}/{self.split_config['non_iid_split_name']}/genotypes/split_{i}"
            prefix_list.append(prefix)
            df.loc[(df.split == i), ['FID', 'IID', 'sex']].to_csv(split_id_path, index=False, sep='\t')
            
            if make_pgen:
                self.make_split_pgen(split_id_path, prefix)
        
        return prefix_list
        
