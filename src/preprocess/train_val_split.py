import os
from typing import List
import hydra
from omegaconf import DictConfig
from os import symlink

import pandas
from sklearn.model_selection import KFold, train_test_split, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from numpy import array_split, array, cumsum
import pandas as pd

from configs.split_config import FOLDS_NUMBER
from utils.split import Split


class WBSplitter:
    def __init__(self, ethnic_split: Split, new_split: Split, n_nodes: int, array_split_arg, n_folds: int = FOLDS_NUMBER):
        """
        Splits the white british node of the ethnic split into a number of nodes
        in a new split using numpy's array_split.

        Args:
            ethnic_split: Split object for ethnic split ID paths (dummy phenotypes)
            new_split: Split object for new split ID paths (dummy phenotypes)
            n_nodes: Number of nodes in the new split
            array_split_args: either the number or uniform splits or a list of share sizes
                              for the new split.
            n_folds: Number of CV folds
        """
        self.ethnic_split = ethnic_split
        self.new_split = new_split
        self.n_nodes = n_nodes
        assert isinstance(array_split_arg, int) or isinstance(array_split_arg, list)
        self.array_split_arg = array_split_arg
        self.n_folds = n_folds

    def split_ids(self):
        for fold_index in range(self.n_folds):
            for part_name in ["train", "val"]:
                path = self.ethnic_split.get_ids_path(node_index=0, fold_index=fold_index, part_name=part_name)
                ids = pandas.read_table(path).loc[:, ['FID', 'IID']]

                if isinstance(self.array_split_arg, int):
                    split_ids_list = array_split(ids, self.array_split_arg)
                elif isinstance(self.array_split_arg, list):
                    split_ids_list = array_split(ids, (cumsum(array(self.array_split_arg))*len(ids)).astype(int))

                assert len(ids) == sum([len(split_ids) for split_ids in split_ids_list])

                for node_index, split_ids in enumerate(split_ids_list):
                    out_path = self.new_split.get_ids_path(node_index=node_index, fold_index=fold_index, part_name=part_name)
                    split_ids.to_csv(out_path, sep='\t', index=False)

            # Symlink for test ids
            for node_index in range(self.n_nodes):
                source_path = self.ethnic_split.get_ids_path(node_index=0, fold_index=fold_index, part_name='test')
                destination_path = self.new_split.get_ids_path(node_index=node_index, fold_index=fold_index,
                                                               part_name='test')
                if not os.path.exists(destination_path):
                    symlink(source_path, destination_path)


class CVSplitter:
    def __init__(self, split: Split) -> None:
        """Splits PCs, phenotypes and covariates into folds.
        Merges PCs and covariates for GWAS.
        Extracts phenotypes.

        Args:
            split (Split): Split object for phenotype, PC and covariates file paths manipulation
        """
        self.split = split

    def split_ids(self, ids_path: str = None, node_index: int = None, node: str = None, y: pd.Series = None, random_state: int = 34, num_folds: int = FOLDS_NUMBER):
        """
        Splits sample ids into K-fold cv for each node. At each fold, 1/Kth goes to test data, 1/Kth (randomly) to val
        and the rest to train

        Args:
            node_index (int): Index of node
            node_index (int): Alternatively, node name
            y: y can be passed to trigger StratifiedKFold instead KFold
            random_state (int): Fixed random_state for train_test_split sklearn function
            num_folds (int): number of folds
        """
        if ids_path is None:
            ids_path = self.split.get_source_ids_path(fn=f'{node_index}.csv' if node_index is not None else f'{node}.tsv')
        # we do not need sex here
        ids = pandas.read_table(ids_path).rename(columns={'#IID': 'IID'}).filter(['FID', 'IID'])

        if y is None:
            # regular KFold
            kfsplit = KFold(n_splits=num_folds, shuffle=True, random_state=random_state).split(ids)
        else:
            # stratified KFold, for categorical and possibly binary phenotypes
            y = y.reindex(pd.Index(ids['IID']))
            kfsplit = StratifiedKFold(n_splits=num_folds, shuffle=True, random_state=random_state).split(ids, y=y)
        for fold_index, (train_val_indices, test_indices) in enumerate(kfsplit):
            train_indices, val_indices = train_test_split(train_val_indices,
                                                          train_size=(FOLDS_NUMBER - 2) / (FOLDS_NUMBER - 1),
                                                          random_state=random_state,
                                                          stratify=None if y is None else y.iloc[train_val_indices])

            for indices, part in zip([train_indices, val_indices, test_indices], ['train', 'val', 'test']):
                out_path = self.split.get_ids_path(node_index=node_index, node=node, fold_index=fold_index, part_name=part)
                ids.iloc[indices, :].to_csv(out_path, sep='\t', index=False)


    def split_phenotypes(self, node_index: int) -> None:
        """
        Extracts train or val subset of samples from file with phenotypes and covariates

        Args:
            node_index (int): Index of particular node

        Returns:
            str: Path to extracted subset of samples with phenotypes and covariates
        """
        phenotype = pandas.read_table(self.split.get_source_phenotype_path(node_index))

        for fold_index in range(FOLDS_NUMBER):
            for part in ['train', 'val', 'test']:

                fold_indices = pandas.read_table(self.split.get_ids_path(node_index=node_index, fold_index=fold_index, part_name=part))
                part_phenotype = phenotype.merge(fold_indices, how='inner', on=['FID', 'IID'])

                out_path = self.split.get_cov_pheno_path(node_index=node_index, fold_index=fold_index, part=part)
                part_phenotype.to_csv(out_path, sep='\t', index=False)


    def split_pca(self, node_index: int) -> None:
        """
        Extracts train or val subset of samples from file with principal components
        Args:
            node_index (int): Index of particular node

        Returns:
            str: Path to extracted subset of samples with PCs
        """
        pca = pandas.read_table(self.split.get_source_pca_path(node_index))
        pca.rename({'#FID': 'FID'}, axis='columns', inplace=True)

        for fold_index in range(FOLDS_NUMBER):
            for part in ['train', 'val', 'test']:

                fold_indices = pandas.read_table(self.split.get_ids_path(node_index=node_index, fold_index=fold_index, part_name=part))

                fold_pca = pca.merge(fold_indices, how='inner', on=['FID', 'IID'])
                fold_pca.to_csv(self.split.get_pca_path(node_index=node_index, fold_index=fold_index, part=part), sep='\t', index=False)

    def prepare_cov_and_phenotypes(self, node_index: int):
        """Transforms phenotype+covariates and pca files into phenotype and pca+covariates files for each fold.

        Args:
            node_index (int): Index of node
        """
        for fold_index in range(FOLDS_NUMBER):
            for part in ['train', 'val', 'test']:

                pca_path = self.split.get_pca_path(node_index=node_index, fold_index=fold_index, part=part)
                cov_pheno_path = self.split.get_cov_pheno_path(node_index=node_index, fold_index=fold_index, part=part)
                pca_cov_path = self.split.get_pca_cov_path(node_index=node_index, fold_index=fold_index, part=part)
                phenotype_path = self.split.get_phenotype_path(node_index=node_index, fold_index=fold_index, part=part)

                self.prepare_cov_and_phenotype_for_fold(pca_path, cov_pheno_path, pca_cov_path, phenotype_path)

    @staticmethod
    def prepare_cov_and_phenotype_for_fold(
            pca_path: str,
            cov_pheno_path: str,
            pca_cov_path: str,
            phenotype_path: str
        ):

        """Transforms phenotype+covariates and pca files into phenotype and pca+covariates files.
        This is required by plink 2.0 --glm command

        Args:
            pca_path (str): Path to PCA eigenvec file computed by plink 2.0
            cov_pheno_path (str): Path to phenotype and covariates file prepared with ukb_loader
            pca_cov_path (str): Path where all covariates including PCs will be stored
            phenotype_path (str): Path with only phenotype data

        """
        pca = pandas.read_table(pca_path)
        cov_pheno = pandas.read_table(cov_pheno_path)
        cov_columns = list(cov_pheno.columns)[2:-1]
        pheno_column = cov_pheno.columns[-1]
        # print(f'COV_PHENO_COLUMNS are: {cov_columns}')
        merged = pca.merge(cov_pheno, how='inner', on=['FID', 'IID'])

        pca_cov = merged.loc[:, ['FID', 'IID'] + [f'PC{i}' for i in range(1, 11)] + cov_columns]
        pca_cov.fillna(pca_cov.mean(), inplace=True)
        phenotype = merged.loc[:, ['FID', 'IID'] + [pheno_column]]

        phenotype.to_csv(phenotype_path, sep='\t', index=False)
        pca_cov.to_csv(pca_cov_path, sep='\t', index=False)


    def standardize_covariates(self, node_index: int, covariates: List[str] = None):
        """Z-standardizes {covariates} for each fold and particular node {node_index}

        Args:
            node_index (int): Index of node
            covariates (List[str], optional): Covariates to standardize. If None, every covariate will be standardized. Defaults to None.
        """
        for fold_index in range(FOLDS_NUMBER):
            self.standardize(
                    self.split.get_pca_cov_path(node_index, fold_index, 'train'),
                    self.split.get_pca_cov_path(node_index, fold_index, 'val'),
                    self.split.get_pca_cov_path(node_index, fold_index, 'test'),
                    covariates
            )


    def standardize(self, train_path: str, val_path: str, test_path: str, columns: List[str]):
        """
        Infers mean and std from columns in {train_path} and standardizes both train, test and val columns in-place
        TODO: think about non-iid data!!!

        Args:
            train_path (str): Path to .tsv file with train data. First two columns should be FID, IID
            val_path (str): Path to .tsv file with val data. First two columns should be FID, IID
            columns (List[str]): List of columns to standardize. By default all columns except FID and IID will be standardized.
        """
        train_data = pandas.read_table(train_path)
        val_data = pandas.read_table(val_path)
        test_data = pandas.read_table(test_path)

        scaler = StandardScaler()
        if columns is None:
            train_data.iloc[:, 2:] = scaler.fit_transform(train_data.iloc[:, 2:]) # 0,1 are FID, IID
            val_data.iloc[:, 2:] = scaler.transform(val_data.iloc[:, 2:])
            test_data.iloc[:, 2:] = scaler.transform(test_data.iloc[:, 2:])
            print('Means and stds are: ')
            print({col: f'mean {mean:.4f}\tstd {scale:.4f}' for col, mean, scale in zip(train_data.columns[2:], scaler.mean_, scaler.scale_)})
        else:
            train_data.loc[:, columns] = scaler.fit_transform(train_data.loc[:, columns])
            val_data.loc[:, columns] = scaler.transform(val_data.loc[:, columns])
            test_data.loc[:, columns] = scaler.transform(test_data.loc[:, columns])
            print('Means and stds are: ')
            print({col: f'mean {mean:.4f}, std {scale:.4f}' for col, mean, scale in zip(columns, scaler.mean_, scaler.scale_)})

        train_data.to_csv(train_path, sep='\t', index=False)
        val_data.to_csv(val_path, sep='\t', index=False)
        test_data.to_csv(test_path, sep='\t', index=False)


@hydra.main(config_path='configs', config_name='split')
def main(cfg: DictConfig):

    split = Split(cfg.split_dir, cfg.phenotype.name, cfg.node_count, FOLDS_NUMBER)
    cv = CVSplitter(split)

    for node_index in range(cfg.node_count):

        print(f'Node: {node_index}')
        cv.split_ids(node_index, cfg.random_state)
        print(f'ids were splitted')

        cv.split_phenotypes(node_index)
        print(f'phenotypes were splitted')

        cv.split_pca(node_index)
        print(f'PCs were splitted')

        cv.prepare_cov_and_phenotypes(node_index)
        print(f'covariates and phenotypes were prepared')

        cv.standardize_covariates(node_index, cfg.zstd_covariates)
        print(f'covariates {cfg.zstd_covariates} were standardized')

if __name__ == '__main__':
    main()
