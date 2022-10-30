from typing import Optional
import numpy
import pandas
from pgenlib import PgenReader


def load_from_pgen(pfile_path: str, gwas_path: str, snp_count: int, sample_indices=None, missing='zero') -> numpy.ndarray:
    """
    Loads genotypes from .pgen into numpy array and selects top {snp_count} snps

    Args:
        pfile_path (str): Path to plink 2.0 .pgen, .pvar, .psam dataset. It should not have a .pgen extension.
        gwas_path (str): Path to plink 2.0 GWAS results file generated by plink 2.0 --glm. 
        snp_count (int): Number of most significant SNPs to load. If None then load all SNPs
        sample_indices (numpy.ndarray): Indices of which samples to load genotypes for. Default of None loads all indices.
        missing (str): Strategy of filling missing values. Default is 'zero', i.e. homozygous reference value. Other is 'mean'.

    Raises:
        ValueError: If snp_count is greated than number of SNPs in .pgen

    Returns:
        numpy.ndarray: An int8 sample-major array with {snp_count} genotypes
    """    
    reader = PgenReader((pfile_path + '.pgen').encode('utf-8'), sample_subset=sample_indices)
    max_snp_count = reader.get_variant_ct()
    
    if sample_indices is not None:
        sample_count = len(sample_indices)
        sample_indices = numpy.arange(sample_count).astype(numpy.uint32)
    else:
        sample_count = reader.get_raw_sample_ct()
    
    if snp_count is not None and snp_count > max_snp_count:
        raise ValueError(f'snp_count {snp_count} should be not greater than max_snp_count {max_snp_count}')
    
    snp_count = max_snp_count if snp_count is None else snp_count
    array = -numpy.ones((sample_count, snp_count), dtype=numpy.int8)
    
    if snp_count is None or snp_count == max_snp_count:
        reader.read_range(0, max_snp_count, array, sample_maj=True)
    else:
        snp_indices = get_snp_list(pfile_path, gwas_path, snp_count)
        reader.read_list(snp_indices, array, sample_maj=True)
    if any(array -= -1):
        raise ValueError('Not all requested SNPs were found in the genotype file')
    if missing == 'zero':
        array[array == -9] = 0
    elif missing == 'mean':
        array = numpy.where(numpy.isnan(array), numpy.nanmean(array, axis=0), array) 
    return array


def load_phenotype(phenotype_path: str, out_type = numpy.float32, encode = False) -> numpy.ndarray:
    """
    :param phenotype_path: Phenotypes location
    :param out_type: convert to type
    :param encode: whether phenotypes are strings and we want to code them as ints)
    """
    data = pandas.read_table(phenotype_path)
    data = data.iloc[:, -1].values.astype(out_type)
    if encode:
        _, data = numpy.unique(data, return_inverse=True)
    return data

def load_covariates(covariates_path: str, load_pcs: bool = False) -> numpy.ndarray:
    data = pandas.read_table(covariates_path)
    if load_pcs:
        to_load = [col for col in data.columns if col not in ['FID', 'IID']]        
    else:
        to_load = [col for col in data.columns if not col.startswith('PC') and col not in ['FID', 'IID']]
    return data.loc[:, to_load].values # First two columns are FID, IID

def get_sample_indices(pfile_path: str, phenotype_path: str, indices_limit: Optional[int] = None) -> numpy.ndarray:
    """Given the prefix to a genotype file and a phenotype file, returns an array 
    indicating which indices of the genotype are present in the phenotype. Used to
    select samples within a genotype file with PgenReader.
    
    Args:
        pfile_path (str): Genotye prefix path
        phenotype_path (str): Path to phenotype (or other) file with IID column.
        indices_limit (Optional[int]): Maximum number of samples to return. Useful for limiting memory usage for the test dataset
    
    Returns:
        numpy.ndarray: Array with list of indices required to load samples present in
            the phenotype from the genotype file.
    """
    psam = pandas.read_table(pfile_path + '.psam').rename(columns={'#IID': 'IID'})
    pheno = pandas.read_table(phenotype_path)
    psam['idx'] = numpy.arange(0, psam.shape[0])
    indices = psam.loc[psam.IID.isin(pheno.IID), 'idx'].values.astype('uint32')
    if indices_limit is not None and indices_limit < indices.shape[0]:
        # we do not care about random subsample for now
        return indices[:indices_limit]
    else:
        return indices 

def get_snp_list(pfile_path: str, gwas_path: str, snp_count: int) -> numpy.ndarray:
    pvar = pandas.read_table(pfile_path + '.pvar')
    gwas = pandas.read_table(gwas_path)
    gwas.sort_values(by='LOG10_P', axis='index', ascending=False, inplace=True)
    snp_ids = set(gwas.ID.values[:snp_count])
    snp_indices = numpy.arange(pvar.shape[0])[pvar.ID.isin(snp_ids)].astype(numpy.uint32)
    return snp_indices
    
