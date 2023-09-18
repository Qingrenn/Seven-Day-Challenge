import argparse

import scipy.io
import torch
import numpy as np
# import time
import os
import wandb

import sys
import json

# parser = argparse.ArgumentParser(description='evaluate')
# parser.add_argument('--name', default='none', type=str, help='gpu_ids: e.g. 0  0,1,2  0,2')
# parser.add_argument('--num', default=0, type=str, help='gpu_ids: e.g. 0  0,1,2  0,2')
# parser.add_argument('--epoch', default='0', type=str, help='gpu_ids: e.g. 0  0,1,2  0,2')
# opt = parser.parse_args()


# os.environ["CUDA_VISIBLE_DEVICES"] = '2'
#######################################################################
# Evaluate

hard_samples = {'easy': [], 'medium': [], 'hard': []}

class Logger(object):
    def __init__(self, filename="Default.log"):
        self.terminal = sys.stdout
        self.log = open(filename, "a")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        pass


def evaluate(qf, ql, qp, gf, gl, gp):
    query = qf.view(-1, 1)
    # print(query.shape)
    score = torch.mm(gf, query)
    score = score.squeeze(1).cpu()
    score = score.numpy()
    # predict index
    index = np.argsort(score)  # from small to large
    index = index[::-1]
    # index = index[0:2000]
    # good index
    query_index = np.argwhere(gl == ql)
    good_index = query_index
    # print(good_index)
    # print(index[0:10])
    junk_index = np.argwhere(gl == -1)

    CMC_tmp = compute_mAP(index, good_index, junk_index, qp, gp)
    return CMC_tmp


def compute_mAP(index, good_index, junk_index, qp, gp):
    global hard_samples

    ap = 0
    cmc = torch.IntTensor(len(index)).zero_()
    if good_index.size == 0:  # if empty
        cmc[0] = -1
        return ap, cmc

    # remove junk_index
    mask = np.in1d(index, junk_index, invert=True)
    index = index[mask]

    # find good_index index
    ngood = len(good_index)
    mask = np.in1d(index, good_index)
    rows_good = np.argwhere(mask == True)
    rows_good = rows_good.flatten()

    # collect hard sample
    right_idx = rows_good[0]
    if right_idx > 0 and right_idx < 10 :
        query_name = os.path.join(*qp.split('/')[-3:])
        gallery_names = gp[index[:right_idx+1]]
        gallery_names = [os.path.join(*n.split('/')[-3:]) for n in gallery_names]
        hard_smaple ={'query': query_name, 'gallery': gallery_names}

        if (right_idx < 5):
            hard_samples['easy'].append(hard_smaple)
        elif (right_idx < 10):
            hard_samples['medium'].append(hard_smaple)

    elif right_idx >= 10 :
        query_name = os.path.join(*qp.split('/')[-3:])
        gallery_names = gp[index[right_idx]]
        hard_smaple ={'query': query_name, 'gallery': gallery_names}
        hard_samples['hard'].append(hard_smaple)


    cmc[rows_good[0]:] = 1
    for i in range(ngood):
        d_recall = 1.0 / ngood
        precision = (i + 1) * 1.0 / (rows_good[i] + 1)
        if rows_good[i] != 0:
            old_precision = i * 1.0 / rows_good[i]
        else:
            old_precision = 1.0
        ap = ap + d_recall * (old_precision + precision) / 2

    return ap, cmc

def collect_hardsamples():
    pass


######################################################################
# result = scipy.io.loadmat('model/MLPNclean/mid_result_160.mat')
result = scipy.io.loadmat('pytorch_result_train_dataset.mat')
query_path = result['query_path']
query_feature = torch.FloatTensor(result['query_f'])
query_label = result['query_label'][0]

gallery_path = result['gallery_path']
gallery_feature = torch.FloatTensor(result['gallery_f'])
gallery_label = result['gallery_label'][0]
multi = os.path.isfile('multi_query.mat')

if multi:
    m_result = scipy.io.loadmat('multi_query.mat')
    mquery_feature = torch.FloatTensor(m_result['mquery_f'])
    mquery_label = m_result['mquery_label'][0]
    mquery_feature = mquery_feature.cuda()

query_feature = query_feature.cuda()
gallery_feature = gallery_feature.cuda()

print(query_feature.shape)
print(gallery_feature.shape)
# print(gallery_feature[0,:])
CMC = torch.IntTensor(len(gallery_label)).zero_()
ap = 0.0
# print(query_label)
for i in range(len(query_label)):
    ap_tmp, CMC_tmp = evaluate(query_feature[i], query_label[i], query_path[i], gallery_feature, gallery_label, gallery_path)
    if CMC_tmp[0] == -1:
        continue
    CMC = CMC + CMC_tmp
    ap += ap_tmp
    # print(i, CMC_tmp[0])

CMC = CMC.float()
CMC = CMC / len(query_label)  # average CMC
print(round(len(gallery_label) * 0.01))
# if opt.num == 0:
#     wandb.init(project="DWDR", name=opt.name, reinit=True, group='experiment-1')

# wandb.log({
#     'Recall@1': CMC[0] * 100,
#     'AP': ap / len(query_label) * 100,
# })

print('Recall@1:%.2f Recall@5:%.2f Recall@10:%.2f Recall@top1:%.2f AP:%.2f' % (
    CMC[0] * 100, CMC[4] * 100, CMC[9] * 100, CMC[round(len(gallery_label) * 0.01)] * 100, ap / len(query_label) * 100))

hardsamplefile = './hardsample/hardsample_train.json'
with open(hardsamplefile, 'w') as f:
        json.dump(hard_samples, f, indent=4)

# txt = "name:{},epoch:{};Recall@1:{:.2f} Recall@5:{:.2f} Recall@10:{:.2f} Recall@top1:{:.2f} AP:{:.2f} ".format(opt.name, opt.epoch,CMC[0] * 100, CMC[4] * 100, CMC[9] * 100, CMC[round(len(gallery_label) * 0.01)] * 100, ap / len(query_label) * 100)




# fw = open("/home/lihaoran/DWDR/model/all.txt", 'a')
# # 这里平时print("test")换成下面这行，就可以输出到文本中了
# fw.write(txt)
# # 换行
# fw.write("\n")

# multiple-query
CMC = torch.IntTensor(len(gallery_label)).zero_()
ap = 0.0
if multi:
    for i in range(len(query_label)):
        mquery_index1 = np.argwhere(mquery_label == query_label[i])
        mquery_index2 = np.argwhere(mquery_cam == query_cam[i])
        mquery_index = np.intersect1d(mquery_index1, mquery_index2)
        mq = torch.mean(mquery_feature[mquery_index, :], dim=0)
        ap_tmp, CMC_tmp = evaluate(mq, query_label[i], query_cam[i], gallery_feature, gallery_label, gallery_cam)
        if CMC_tmp[0] == -1:
            continue
        CMC = CMC + CMC_tmp
        ap += ap_tmp
        # print(i, CMC_tmp[0])
    CMC = CMC.float()
    CMC = CMC / len(query_label)  # average CMC
    print('multi Rank@1:%f Rank@5:%f Rank@10:%f mAP:%f' % (CMC[0], CMC[4], CMC[9], ap / len(query_label)))

