from abc import abstractmethod
from ukb_loader import UKBDataLoader
from numpy.random import seed, choice
import pandas as pd
pd.options.mode.chained_assignment = None # Shush
import os

from configs.global_config import data_root, sample_qc_ids_path, ukb_loader_dir, ukb_pfile_path, areas_path, superpopulations_path
from configs.split_config import non_iid_split_name, split_map, assessment_centre_code_map, assessment_centre_split_name, heterogeneous_split_codes, heterogeneous_split_name, n_heterogeneous_nodes, n_subsample_nodes, n_subsample_samples, random_seed
from utils.plink import run_plink

class SplitBase(object):
    def __init__(self):
        pass

    @abstractmethod
    def split(self):
        pass
    
    def get_ethnic_background(self) -> pd.DataFrame:
        """
        Loads the ethnic background phenotype for samples that passed initial QC,
        drops rows with missing values and returns a DataFrame formatted to be used
        for downstream analysis with PLINK.
        """
        loader = UKBDataLoader(ukb_loader_dir, 'split', '21000', ['31'])
        df = pd.concat((loader.load_train(), loader.load_val(), loader.load_test()))
        df.columns = ['sex', 'ethnic_background']
        df = df.loc[~df.ethnic_background.isna()]
        df.ethnic_background = df.ethnic_background.astype('int')
        
        # Include FID/IID fields for plink to play nice with the output files
        df['FID'] = df.index
        df['IID'] = df.index
        # Leave only those samples that passed population QC
        sample_qc_ids = pd.read_table(f'{sample_qc_ids_path}.id', index_col='IID')
        df = df.loc[df.index.intersection(sample_qc_ids.index)]
        
        return df
    
    def make_split_pgen(self, split_id_path: str, out_prefix: str, bin_file_type='--pfile', bin_file=ukb_pfile_path) -> None:
        run_plink(args_dict={bin_file_type: bin_file,
                             '--out': out_prefix,
                             '--keep': split_id_path},
                  args_list=['--make-pgen'])
        
        
class SplitNonIID(SplitBase):
    def split(self, make_pgen=True):
        df = self.get_ethnic_background()
        
        # Drop samples with missing/prefer not to answer ethnic background
        df = df[~df.ethnic_background.isin([-1, -3, 0])]
        # Map ethnic backgrounds to our defined splits
        df['split'] = df.ethnic_background.map(split_map)
        
        
        split_id_dir = os.path.join(data_root, non_iid_split_name, 'split_ids')
        genotype_dir = os.path.join(data_root, non_iid_split_name, 'genotypes')
        genotype_node_dirs = [os.path.join(genotype_dir, f"node_{node_index}")
                              for node_index in range(max(list(split_map.values()))+1)]
        
        for dir_ in [split_id_dir, genotype_dir] + genotype_node_dirs:
            os.makedirs(dir_, exist_ok=True)
        
        prefix_list = []
        for i in range(max(list(split_map.values()))+1):
            split_id_path = os.path.join(split_id_dir, f"{i}.csv")
            prefix = os.path.join(genotype_dir, f"node_{i}")
            prefix_list.append(prefix)
            df.loc[(df.split == i), ['FID', 'IID']].to_csv(split_id_path, index=False, sep='\t')
            
            if make_pgen:
                self.make_split_pgen(split_id_path, prefix)
        
        return prefix_list
        
class SplitHeterogeneous(SplitBase):
    def split(self, areas_path=areas_path):
        '''
        Splits white british samples based on a provided table with region codes.
        Args:
        areas_path: path to file with region codes.
        '''
        df = self.get_ethnic_background()
        
        # Drop samples with missing/prefer not to answer ethnic background
        df = df[~df.ethnic_background.isin([-1, -3, 0])]
        # Keep ethnicities included in heterogeneous split
        df = df[df.ethnic_background.isin(heterogeneous_split_codes)]
        
        split_id_dir = os.path.join(data_root, "region_split", 'split_ids')
        
        areas = pd.read_csv(areas_path)
        areas = areas.loc[~areas.nuts118cd.isna()]
        areas.index = areas.IID
        areas = areas.loc[areas.index.intersection(df.index)]

        for i, code in enumerate(sorted(areas.nuts118cd.unique())):
            split_id_path = os.path.join(split_id_dir, f"{i}.csv")
            df.loc[areas.loc[areas.nuts118cd==code].index, ['FID', 'IID']].to_csv(split_id_path, index=False, sep='\t')
            
class SplitTG(SplitBase):
    def split(self, make_pgen=True, superpopulations_path=superpopulations_path):
        '''
        Splits UKB samples based on a provided table with superpopulation codes.
        Args:
        superpopulations_path: path to file with region codes.
        '''
        df = pd.read_table(superpopulations_path)
        df.index = df.IID
        df['FID'] = df.IID
        
        # Keep only samples that passed sample QC
        sample_qc_ids = pd.read_table(f'{sample_qc_ids_path}.id', index_col='IID')
        df = df.loc[df.index.intersection(sample_qc_ids.index)]
        
        split_id_dir = os.path.join(data_root, "tg_split", 'split_ids')
        genotype_dir = os.path.join(data_root, "tg_split", 'genotypes')
        genotype_node_dirs = [os.path.join(genotype_dir, f"node_{node_index}")
                              for node_index in range(max(list(split_map.values()))+1)]
        
        for dir_ in [split_id_dir, genotype_dir] + genotype_node_dirs:
            os.makedirs(dir_, exist_ok=True)

        prefix_list = []
            
        for i in range(max(df.node_index) + n_subsample_nodes + 1):
            split_id_path = os.path.join(split_id_dir, f"{i}.csv")
            
            if i <= max(df.node_index): # Superpopulation node
                df.loc[df.node_index == i, ['FID', 'IID']].to_csv(split_id_path, index=False, sep='\t')
            else: # Subsampled node
                df.loc[df.node_index == 0, ['FID', 'IID']].sample(n_subsample_samples, random_state=i)\
                .to_csv(split_id_path, index=False, sep='\t')
                
            prefix = os.path.join(genotype_dir, f"node_{i}")
            prefix_list.append(prefix)
            
            if make_pgen:
                self.make_split_pgen(split_id_path, prefix)
                
        return prefix_list
    
         
class SplitAssessmentCentre(SplitBase):
    def split(self, make_pgen=True):
        '''
        Splits UKB samples based on Assessment Centres
        '''
        loader = UKBDataLoader(ukb_loader_dir, 'split', '54', ['31'])
        df = pd.concat((loader.load_train(), loader.load_val(), loader.load_test()))
        df['FID'] = df['IID'] = df.index
        
        # Keep only samples that passed sample QC
        sample_qc_ids = pd.read_table(f'{sample_qc_ids_path}.id', index_col='IID')
        df = df.loc[df.index.intersection(sample_qc_ids.index)]
        
        split_id_dir = os.path.join(data_root, assessment_centre_split_name, 'split_ids')
        genotype_dir = os.path.join(data_root, assessment_centre_split_name, 'genotypes')
        genotype_node_dirs = [os.path.join(genotype_dir, f"node_{node_index}")
                              for node_index in range(len(assessment_centre_code_map))]
        
        for dir_ in [split_id_dir, genotype_dir] + genotype_node_dirs:
            os.makedirs(dir_, exist_ok=True)

        prefix_list = []
            
        for i, code in enumerate(assessment_centre_code_map.keys()):
            split_id_path = os.path.join(split_id_dir, f"{i}.csv")
            df.loc[df['54'] == float(code), ['FID', 'IID']].to_csv(split_id_path, index=False, sep='\t')
                
            prefix = os.path.join(genotype_dir, f"node_{i}")
            prefix_list.append(prefix)
            
            if make_pgen:
                self.make_split_pgen(split_id_path, prefix)
                
        return prefix_list
    
        
        
        
