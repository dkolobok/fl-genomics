import numpy as np
import torch
from sklearn.metrics import r2_score, roc_auc_score
from torch.nn.functional import mse_loss, cross_entropy, binary_cross_entropy

MEAN_PHENO_DICT = {'standing_height': 170.0,
                   'ebmd': -0.33}

QUANTITATIVE_PHENO_LIST = [
        'standing_height',
        'platelet_volume',
        'erythrocyte_count',
        'triglycerides',
        'hdl_cholesterol',
        'vitamin_d',
        'creatinine',
        'alkaline_phosphatase',
        'cystatin_c',
        'gamma_glutamyltransferase',
        'ebmd',
        'apolipoprotein_a',
        'shbg']

BINARY_PHENO_LIST = [
        'asthma',
        'hypothyroidism', 
        'hypertension',
        'diabetes',
        'psoriasis',
        'rhinitis',
        'osteoarthritis',
        'depression',
        'gastric_reflux',
        'angina',
        'migraine'
        ]

PHENO_TYPE_DICT = {'ancestry': 'discrete',
                   'simulated': 'continuous',
                   'asthma': 'binary',
                   'diabetes': 'binary',
                   'hypertension': 'binary',
                   'hypothyroidism': 'binary'}

TYPE_LOSS_DICT = {'continuous': mse_loss,
                  'discrete': cross_entropy,
                  'binary': binary_cross_entropy}

PHENO_NUMPY_DICT = {'standing_height': np.float32,
                    'ebmd': np.float32,
                    'ancestry': np.ndarray,
                    'asthma': np.float32,
                    'diabetes': np.float32,
                    'hypertension': np.float32,
                    'hypothyroidism': np.float32,
                    'platelet_volume': np.float32}


PHENO_TYPE_DICT.update({phenotype: 'continuous' for phenotype in QUANTITATIVE_PHENO_LIST})
PHENO_TYPE_DICT.update({phenotype: 'binary' for phenotype in BINARY_PHENO_LIST})
PHENO_NUMPY_DICT.update({phenotype: np.float32 for phenotype in QUANTITATIVE_PHENO_LIST})
PHENO_NUMPY_DICT.update({phenotype: np.float32 for phenotype in BINARY_PHENO_LIST})

def get_accuracy(y_true: np.array, y_pred: torch.tensor) -> float:
    """ Takes predictions, gets most probable class and compares with y to get accuracy """
    return int(torch.sum(torch.max(torch.tensor(y_pred), 1).indices == torch.from_numpy(y_true))) / len(y_true)


TYPE_METRIC_DICT = {'continuous': {'metric_fun': r2_score,
                                   'metric_name': 'r2'},
                    'discrete': {'metric_fun': get_accuracy,
                                 'metric_name': 'accuracy'},
                    'binary': {'metric_fun': roc_auc_score,
                               'metric_name': 'roc_auc'}
                    }
