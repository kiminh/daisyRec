import os
import time
import logging
import logging.config
import argparse
import numpy as np
import pandas as pd
from tqdm import tqdm

from daisy.model.MostPopRecommender import MostPop
from daisy.utils.loader import load_rate, split_test, get_ur
from daisy.utils.metrics import precision_at_k, recall_at_k, map_at_k, hr_at_k, mrr_at_k, ndcg_at_k

if __name__ == '__main__':
    # load logger configuration
    logging.config.fileConfig("./log.conf")
    logger_name = 'MostPop'
    logger = logging.getLogger(logger_name)
    logger.debug('MostPop experiment running...')

    parser = argparse.ArgumentParser(description='Most-Popular recommender test')
    # common settings
    parser.add_argument('--dataset', 
                        type=str, 
                        default='ml-100k', 
                        help='select dataset')
    parser.add_argument('--prepro', 
                        type=str, 
                        default='origin', 
                        help='dataset preprocess op.: origin/5core/10core')
    parser.add_argument('--topk', 
                        type=int, 
                        default=50, 
                        help='top number of recommend list')
    parser.add_argument('--test_method', 
                        type=str, 
                        default='tfo', 
                        help='method for split test,options: loo/fo/tfo/tloo')
    parser.add_argument('--test_size', 
                        type=float, 
                        default=.2, 
                        help='split ratio for test set')
    parser.add_argument('--val_method', 
                        type=str, 
                        default='tfo', 
                        help='validation method, options: cv, tfo, loo, tloo')
    parser.add_argument('--fold_num', 
                        type=int, 
                        default=5, 
                        help='No. of folds for cross-validation')
    parser.add_argument('--cand_num', 
                        type=int, 
                        default=1000, help='No. of candidates item for predict')
    parser.add_argument('--sample_method', 
                        type=str, 
                        default='uniform', 
                        help='negative sampling method, options: uniform, item-ascd, item-desc')
    # algo settings
    parser.add_argument('--pop_n', 
                        type=int, 
                        default=400, 
                        help='Initial selected number of Most-popular')
    args = parser.parse_args()

    time_log = open('time_log.txt', 'a')

    '''Test Process for Metrics Exporting'''
    # df, user_num, item_num = load_rate(args.dataset, args.prepro)
    # train_set, test_set = split_test(df, args.test_method, args.test_size)

    # temporary used for tuning test result
    train_set = pd.read_csv(f'./experiment_data/train_{args.dataset}_{args.prepro}_{args.test_method}.dat')
    test_set = pd.read_csv(f'./experiment_data/test_{args.dataset}_{args.prepro}_{args.test_method}.dat')
    if args.dataset in ['yelp']:
        train_set['timestamp'] = pd.to_datetime(train_set['timestamp'])
        test_set['timestamp'] = pd.to_datetime(test_set['timestamp'])
    df = pd.concat([train_set, test_set], ignore_index=True)
    user_num = df['user'].nunique()
    item_num = df['item'].nunique()
    
    # get ground truth
    test_ur = get_ur(test_set)
    total_train_ur = get_ur(train_set)
    
    print('='*50, '\n')

    s_time = time.time()

    print('Start Calculating Metrics......')
    # get predict result
    # retrain model by the whole train set
    # build recommender model
    model = MostPop(args.pop_n)
    model.fit(train_set)

    elapsed_time = time.time() - s_time
    time_log.write(f'{args.dataset}_{args.prepro}_{args.test_method}_mostpop_{args.sample_method},{elapsed_time:.4f}' + '\n')
    time_log.close()

    preds = model.predict(test_ur, total_train_ur, args.topk)

    # convert rank list to binary-interaction
    for u in preds.keys():
        preds[u] = [1 if i in test_ur[u] else 0 for i in preds[u]]

    # process topN list and store result for reporting KPI
    print('Save metric@k result to res folder...')
    result_save_path = f'./res/{args.dataset}/'
    if not os.path.exists(result_save_path):
        os.makedirs(result_save_path)

    res = pd.DataFrame({'metric@K': ['pre', 'rec', 'hr', 'map', 'mrr', 'ndcg']})

    for k in [1, 5, 10, 20, 30, 50]:
        if k > args.topk:
            continue
        tmp_preds = preds.copy()        
        tmp_preds = {key: rank_list[:k] for key, rank_list in tmp_preds.items()}

        pre_k = np.mean([precision_at_k(r, k) for r in tmp_preds.values()])
        rec_k = recall_at_k(tmp_preds, test_ur, k)
        hr_k = hr_at_k(tmp_preds, test_ur)
        map_k = map_at_k(tmp_preds.values())
        mrr_k = mrr_at_k(tmp_preds, k)
        ndcg_k = np.mean([ndcg_at_k(r, k) for r in tmp_preds.values()])

        if k == 10:
            print(f'Precision@{k}: {pre_k:.4f}')
            print(f'Recall@{k}: {rec_k:.4f}')
            print(f'HR@{k}: {hr_k:.4f}')
            print(f'MAP@{k}: {map_k:.4f}')
            print(f'MRR@{k}: {mrr_k:.4f}')
            print(f'NDCG@{k}: {ndcg_k:.4f}')

        res[k] = np.array([pre_k, rec_k, hr_k, map_k, mrr_k, ndcg_k])

    res.to_csv(f'{result_save_path}{args.prepro}_{args.test_method}_pop_{args.sample_method}.csv', index=False)
    print('='* 20, ' Done ', '='*20)
