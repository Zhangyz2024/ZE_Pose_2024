import torch
from torch import multiprocessing
pool = torch.multiprocessing.Pool(torch.multiprocessing.cpu_count(), maxtasksperchild=1)
import numpy as np
import os, sys
from utils.utils import AverageMeter
from utils.eval import calc_all_errs, Evaluation
from utils.img import im_norm_255, vis_err
import cv2
import ref
from progress.bar import Bar
import os
import utils.fancy_logger as logger
from utils.tictoc import tic, toc
from builtins import input
from utils.fs import mkdir_p
from scipy.linalg import logm
import numpy.linalg as LA
import time
import matplotlib.pyplot as plt
from numba import jit, njit

def test(epoch, cfg, data_loader, model, obj_vtx, obj_info, criterions):

    model.eval()
    Eval = Evaluation(cfg.dataset, obj_info, obj_vtx)

    preds = {}
    Loss = AverageMeter()
    Loss_rot = AverageMeter()
    Loss_trans = AverageMeter()
    num_iters = len(data_loader)
    bar = Bar('{}'.format(cfg.pytorch.exp_id[-60:]), max=num_iters)

    time_monitor = False
    vis_dir = os.path.join(cfg.pytorch.save_path, 'test_vis_{}'.format(epoch))
    if not os.path.exists(vis_dir):
        os.makedirs(vis_dir)

    for i, (obj, obj_id, inp, pose, c_box, s_box, box, trans_local, depth_test_pth) in enumerate(data_loader):
        if cfg.pytorch.gpu > -1:
            inp_var = inp.cuda(cfg.pytorch.gpu, async=True).float()
        else:
            inp_var = inp.float()

        bs = len(inp)
        # forward propagation
        T_begin = time.time()
        pred_rot = model(inp_var)
        T_end = time.time() - T_begin
        if time_monitor:
            logger.info("time for a batch forward of resnet model is {}".format(T_end))

        if i % cfg.test.disp_interval == 0:
            # input image
            inp_rgb = (inp[0].cpu().numpy().copy() * 255)[[2, 1, 0], :, :].astype(np.uint8)
            cfg.writer.add_image('input_image', inp_rgb, i)
            cv2.imwrite(os.path.join(vis_dir, '{}_inp.png'.format(i)), inp_rgb.transpose(1,2,0)[:, :, ::-1])
            if 'rot' in cfg.pytorch.task.lower():
                # coordinates map
                pred_coor = pred_rot[0, 0:3].data.cpu().numpy().copy()
                pred_coor[0] = im_norm_255(pred_coor[0])
                pred_coor[1] = im_norm_255(pred_coor[1])
                pred_coor[2] = im_norm_255(pred_coor[2])
                pred_coor = np.asarray(pred_coor, dtype=np.uint8)
                #cfg.writer.add_image('test_coor_x_pred', np.expand_dims(pred_coor[0], axis=0), i)
                #cfg.writer.add_image('test_coor_y_pred', np.expand_dims(pred_coor[1], axis=0), i)
                #cfg.writer.add_image('test_coor_z_pred', np.expand_dims(pred_coor[2], axis=0), i)
                # gt_coor = target[0, 0:3].data.cpu().numpy().copy()
                # gt_coor[0] = im_norm_255(gt_coor[0])
                # gt_coor[1] = im_norm_255(gt_coor[1])
                # gt_coor[2] = im_norm_255(gt_coor[2])
                # gt_coor = np.asarray(gt_coor, dtype=np.uint8)
                # cfg.writer.add_image('test_coor_x_gt', np.expand_dims(gt_coor[0], axis=0), i)
                # cfg.writer.add_image('test_coor_y_gt', np.expand_dims(gt_coor[1], axis=0), i)
                # cfg.writer.add_image('test_coor_z_gt', np.expand_dims(gt_coor[2], axis=0), i)
                # confidence map
                pred_conf = pred_rot[0, 3].data.cpu().numpy().copy()
                pred_conf = (im_norm_255(pred_conf)).astype(np.uint8)
                cfg.writer.add_image('test_conf_pred', np.expand_dims(pred_conf, axis=0), i)
                # gt_conf = target[0, 3].data.cpu().numpy().copy()
                # cfg.writer.add_image('test_conf_gt', np.expand_dims(gt_conf, axis=0), i)

        if 'rot' in cfg.pytorch.task.lower():
            pred_coor = pred_rot[:, 0:3].data.cpu().numpy().copy()
            pred_conf = pred_rot[:, 3].data.cpu().numpy().copy()
            if cfg.train.split_num > 1:
                pred_conf_x1 = pred_rot[:, 4].data.cpu().numpy().copy()
                pred_conf_y1 = pred_rot[:, 5].data.cpu().numpy().copy()
                pred_conf_z1 = pred_rot[:, 6].data.cpu().numpy().copy()
            if cfg.train.split_num > 2:
                pred_conf_x2 = pred_rot[:, 7].data.cpu().numpy().copy()
                pred_conf_y2 = pred_rot[:, 8].data.cpu().numpy().copy()
                pred_conf_z2 = pred_rot[:, 9].data.cpu().numpy().copy()
            if cfg.train.split_num > 4:
                pred_conf_x3 = pred_rot[:, 10].data.cpu().numpy().copy()
                pred_conf_y3 = pred_rot[:, 11].data.cpu().numpy().copy()
                pred_conf_z3 = pred_rot[:, 12].data.cpu().numpy().copy()

        if 'trans' in cfg.pytorch.task.lower():
            pred_trans = pred_trans.data.cpu().numpy().copy()
        else:
            pred_trans = np.zeros(bs)

        if cfg.train.split_num == 1:
            col = list(zip(obj, obj_id.numpy(), pred_coor, pred_conf, pred_trans, pose.numpy(), c_box.numpy(), s_box.numpy(), box.numpy(), depth_test_pth))
        elif cfg.train.split_num == 2:
            col = list(zip(obj, obj_id.numpy(), pred_coor, pred_conf, pred_conf_x1, pred_conf_y1, pred_conf_z1, pred_trans, pose.numpy(), c_box.numpy(), s_box.numpy(), box.numpy()))
        elif cfg.train.split_num > 2 and cfg.train.split_num <= 4:
            col = list(zip(obj, obj_id.numpy(), pred_coor, pred_conf, pred_conf_x1, pred_conf_y1, pred_conf_z1, pred_conf_x2, pred_conf_y2, pred_conf_z2, \
                                                                                            pred_trans, pose.numpy(), c_box.numpy(), s_box.numpy(), box.numpy()))
        elif cfg.train.split_num > 4 and cfg.train.split_num <= 8:
            col = list(zip(obj, obj_id.numpy(), pred_coor, pred_conf, pred_conf_x1, pred_conf_y1, pred_conf_z1, pred_conf_x2,pred_conf_y2, pred_conf_z2, \
                                                  pred_conf_x3, pred_conf_y3, pred_conf_z3, pred_trans, pose.numpy(), c_box.numpy(), s_box.numpy(), box.numpy()))

        for idx in range(len(col)):
            if cfg.train.split_num == 1:
                obj_, obj_id_, pred_coor_, pred_conf_, pred_trans_, pose_gt, c_box_, s_box_, box_, depth_test_pth_ = col[idx]
            elif cfg.train.split_num == 2:
                obj_, obj_id_, pred_coor_, pred_conf_, pred_conf_x1_, pred_conf_y1_, pred_conf_z1_, pred_trans_, pose_gt, c_box_, s_box_, box_ = col[idx]
            elif cfg.train.split_num > 2 and cfg.train.split_num <= 4:
                obj_, obj_id_, pred_coor_, pred_conf_, pred_conf_x1_, pred_conf_y1_, pred_conf_z1_, pred_conf_x2_, pred_conf_y2_, pred_conf_z2_, \
                                                                                                    pred_trans_, pose_gt, c_box_, s_box_, box_ = col[idx]
            elif cfg.train.split_num > 4 and cfg.train.split_num <= 8:
                obj_, obj_id_, pred_coor_, pred_conf_, pred_conf_x1_, pred_conf_y1_, pred_conf_z1_, pred_conf_x2_, pred_conf_y2_, pred_conf_z2_, \
                                                       pred_conf_x3_, pred_conf_y3_, pred_conf_z3_, pred_trans_, pose_gt, c_box_, s_box_, box_ = col[idx]
            T_begin = time.time()
            if 'rot' in cfg.pytorch.task.lower():
                # building 2D-3D correspondences
                pred_coor_ = pred_coor_.transpose(1, 2, 0)
                #pred_coor_[:, :, 0] = pred_coor_[:, :, 0] * abs(obj_info[obj_id_]['min_x'])
                #pred_coor_[:, :, 1] = pred_coor_[:, :, 1] * abs(obj_info[obj_id_]['min_y'])
                #pred_coor_[:, :, 2] = pred_coor_[:, :, 2] * abs(obj_info[obj_id_]['min_z'])
                #pred_coor_= pred_coor_.tolist()
                eroMask = False
                if eroMask:
                    kernel = np.ones((3, 3), np.uint8)
                    pred_conf_ = cv2.erode(pred_conf_, kernel)
                pred_conf_ = (pred_conf_ - pred_conf_.min()) / (pred_conf_.max() - pred_conf_.min())
                pred_conf_ = pred_conf_.tolist()
                if cfg.train.split_num > 1:
                    pred_conf_x1_ = (pred_conf_x1_ - pred_conf_x1_.min()) / (pred_conf_x1_.max() - pred_conf_x1_.min())
                    pred_conf_x1_ = pred_conf_x1_.tolist()
                    pred_conf_y1_ = (pred_conf_y1_ - pred_conf_y1_.min()) / (pred_conf_y1_.max() - pred_conf_y1_.min())
                    pred_conf_y1_ = pred_conf_y1_.tolist()
                    pred_conf_z1_ = (pred_conf_z1_ - pred_conf_z1_.min()) / (pred_conf_z1_.max() - pred_conf_z1_.min())
                    pred_conf_z1_ = pred_conf_z1_.tolist()
                if cfg.train.split_num > 2:
                    pred_conf_x2_ = (pred_conf_x2_ - pred_conf_x2_.min()) / (pred_conf_x2_.max() - pred_conf_x2_.min())
                    pred_conf_x2_ = pred_conf_x2_.tolist()
                    pred_conf_y2_ = (pred_conf_y2_ - pred_conf_y2_.min()) / (pred_conf_y2_.max() - pred_conf_y2_.min())
                    pred_conf_y2_ = pred_conf_y2_.tolist()
                    pred_conf_z2_ = (pred_conf_z2_ - pred_conf_z2_.min()) / (pred_conf_z2_.max() - pred_conf_z2_.min())
                    pred_conf_z2_ = pred_conf_z2_.tolist()
                if cfg.train.split_num > 4:
                    pred_conf_x3_ = (pred_conf_x3_ - pred_conf_x3_.min()) / (pred_conf_x3_.max() - pred_conf_x3_.min())
                    pred_conf_x3_ = pred_conf_x3_.tolist()
                    pred_conf_y3_ = (pred_conf_y3_ - pred_conf_y3_.min()) / (pred_conf_y3_.max() - pred_conf_y3_.min())
                    pred_conf_y3_ = pred_conf_y3_.tolist()
                    pred_conf_z3_ = (pred_conf_z3_ - pred_conf_z3_.min()) / (pred_conf_z3_.max() - pred_conf_z3_.min())
                    pred_conf_z3_ = pred_conf_z3_.tolist()

                select_pts_2d = []
                select_pts_3d = []
                c_w = int(c_box_[0])
                c_h = int(c_box_[1])
                s = int(s_box_)
                w_begin = c_w - s / 2.
                h_begin = c_h - s / 2.
                w_unit = s * 1.0 / cfg.dataiter.out_res
                h_unit = s * 1.0 / cfg.dataiter.out_res

                max_x = abs(obj_info[obj_id_]['min_x'])
                max_y = abs(obj_info[obj_id_]['min_y'])
                max_z = abs(obj_info[obj_id_]['min_z'])

                if cfg.train.split_num == 1:
                    for x in range(cfg.dataiter.out_res):
                        for y in range(cfg.dataiter.out_res):
                            if pred_conf_[x][y] < cfg.test.mask_threshold:
                                continue
                            if abs(pred_coor_[x][y][0]) < max_x and abs(pred_coor_[x][y][1]) < max_y and \
                                    abs(pred_coor_[x][y][2]) < max_z:
                                continue
                            select_pts_2d.append([w_begin + y * w_unit, h_begin + x * h_unit])
                            select_pts_3d.append(pred_coor_[x][y])

                elif cfg.train.split_num == 2:
                    max_xyz = [max_x, max_y, max_z]
                    pred_conf_xyz1 = np.dstack([pred_conf_x1_, pred_conf_y1_, pred_conf_z1_])
                    low_th = cfg.test.mask_low_th
                    high_th = cfg.test.mask_high_th

                    for x in range(cfg.dataiter.out_res):
                        for y in range(cfg.dataiter.out_res):
                            unchange = 0
                            if pred_conf_[y][x] < cfg.test.mask_threshold:
                                continue
                            for i in range(3):
                                if pred_conf_xyz1[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = -0.5 * max_xyz[i] * (pred_coor_[y][x][i] + 1)
                                elif pred_conf_xyz1[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = 0.5 * max_xyz[i] * (pred_coor_[y][x][i] + 1)
                                else:
                                    unchange += 1
                            if unchange == 0:
                                select_pts_2d.append([w_begin + x * w_unit, h_begin + y * h_unit])
                                select_pts_3d.append(pred_coor_[y][x])

                elif cfg.train.split_num == 3:

                    max_xyz = [max_x, max_y, max_z]
                    pred_conf_xyz1 = np.dstack([pred_conf_x1_, pred_conf_y1_, pred_conf_z1_])
                    pred_conf_xyz2 = np.dstack([pred_conf_x2_, pred_conf_y2_, pred_conf_z2_])
                    low_th = cfg.test.mask_low_th
                    high_th = cfg.test.mask_high_th

                    for x in range(cfg.dataiter.out_res):
                        for y in range(cfg.dataiter.out_res):
                            unchange = 0
                            if pred_conf_[y][x] < cfg.test.mask_threshold:
                                continue
                            for i in range(3):
                                if pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] < low_th:            #  00
                                    pred_coor_[y][x][i] = -1/3 * max_xyz[i] * (pred_coor_[y][x][i] + 2)
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] > high_th:         #  01
                                    pred_coor_[y][x][i] = 1/3 * max_xyz[i] * (pred_coor_[y][x][i])
                                elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] > high_th:        #  11
                                    pred_coor_[y][x][i] = -1/3 * max_xyz[i] * (pred_coor_[y][x][i] - 2)
                                else:
                                    unchange += 1
                            if unchange == 0:
                                select_pts_2d.append([w_begin + x * w_unit, h_begin + y * h_unit])
                                select_pts_3d.append(pred_coor_[y][x])

                elif cfg.train.split_num == 4:

                    max_xyz = [max_x, max_y, max_z]
                    pred_conf_xyz1 = np.dstack([pred_conf_x1_, pred_conf_y1_, pred_conf_z1_])
                    pred_conf_xyz2 = np.dstack([pred_conf_x2_, pred_conf_y2_, pred_conf_z2_])
                    low_th = cfg.test.mask_low_th
                    high_th = cfg.test.mask_high_th

                    if cfg.train.no_bi == False:
                        for x in range(cfg.dataiter.out_res):
                            for y in range(cfg.dataiter.out_res):
                                unchange = 0
                                if pred_conf_[y][x] < cfg.test.mask_threshold:
                                    continue
                                for i in range(3):
                                    if pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] < low_th:
                                        pred_coor_[y][x][i] = -0.25 * max_xyz[i] * (pred_coor_[y][x][i] + 3)
                                    elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] > high_th:
                                        pred_coor_[y][x][i] = 0.25 * max_xyz[i] * (pred_coor_[y][x][i] - 1)
                                    elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] > high_th:
                                        pred_coor_[y][x][i] = -0.25 * max_xyz[i] * (pred_coor_[y][x][i] - 1)
                                    elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] < low_th:
                                        pred_coor_[y][x][i] = 0.25 * max_xyz[i] * (pred_coor_[y][x][i] + 3)
                                    else:
                                        unchange += 1
                                if unchange == 0:
                                    select_pts_2d.append([w_begin + x * w_unit, h_begin + y * h_unit])
                                    select_pts_3d.append(pred_coor_[y][x])
                    else:
                        for x in range(cfg.dataiter.out_res):
                            for y in range(cfg.dataiter.out_res):
                                unchange = 0
                                if pred_conf_[y][x] < cfg.test.mask_threshold:
                                    continue
                                for i in range(3):
                                    if pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] < low_th:
                                        pred_coor_[y][x][i] = -0.25 * max_xyz[i] * (pred_coor_[y][x][i] + 3)
                                    elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] > high_th:
                                        pred_coor_[y][x][i] = 0.25 * max_xyz[i] * (pred_coor_[y][x][i] - 1)
                                    elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] < low_th:
                                        pred_coor_[y][x][i] = -0.25 * max_xyz[i] * (pred_coor_[y][x][i] - 1)
                                    elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] > high_th:
                                        pred_coor_[y][x][i] = 0.25 * max_xyz[i] * (pred_coor_[y][x][i] + 3)
                                    else:
                                        unchange += 1
                                if unchange == 0:
                                    select_pts_2d.append([w_begin + x * w_unit, h_begin + y * h_unit])
                                    select_pts_3d.append(pred_coor_[y][x])

                elif cfg.train.split_num == 5:
                    max_xyz = [max_x, max_y, max_z]
                    pred_conf_xyz1 = np.dstack([pred_conf_x1_, pred_conf_y1_, pred_conf_z1_])
                    pred_conf_xyz2 = np.dstack([pred_conf_x2_, pred_conf_y2_, pred_conf_z2_])
                    pred_conf_xyz3 = np.dstack([pred_conf_x3_, pred_conf_y3_, pred_conf_z3_])
                    low_th = cfg.test.mask_low_th
                    high_th = cfg.test.mask_high_th

                    for x in range(cfg.dataiter.out_res):
                        for y in range(cfg.dataiter.out_res):
                            unchange = 0
                            if pred_conf_[y][x] < cfg.test.mask_threshold:
                                continue
                            for i in range(3):
                                if pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] < low_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = -0.2 * max_xyz[i] * (pred_coor_[y][x][i] + 4)
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] < low_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = 0.2 * max_xyz[i] * (pred_coor_[y][x][i] - 2)
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = -0.2 * max_xyz[i] * (pred_coor_[y][x][i])
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = 0.2 * max_xyz[i] * (pred_coor_[y][x][i] + 2)
                                elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = -0.2 * max_xyz[i] * (pred_coor_[y][x][i] - 4)
                                else:
                                    unchange += 1
                            if unchange == 0:
                                select_pts_2d.append([w_begin + x * w_unit, h_begin + y * h_unit])
                                select_pts_3d.append(pred_coor_[y][x])

                elif cfg.train.split_num == 6:
                    max_xyz = [max_x, max_y, max_z]
                    pred_conf_xyz1 = np.dstack([pred_conf_x1_, pred_conf_y1_, pred_conf_z1_])
                    pred_conf_xyz2 = np.dstack([pred_conf_x2_, pred_conf_y2_, pred_conf_z2_])
                    pred_conf_xyz3 = np.dstack([pred_conf_x3_, pred_conf_y3_, pred_conf_z3_])
                    low_th = cfg.test.mask_low_th
                    high_th = cfg.test.mask_high_th

                    for x in range(cfg.dataiter.out_res):
                        for y in range(cfg.dataiter.out_res):
                            unchange = 0
                            if pred_conf_[y][x] < cfg.test.mask_threshold:
                                continue
                            for i in range(3):
                                if pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] < low_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = -1/6 * max_xyz[i] * (pred_coor_[y][x][i] + 5)
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] < low_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = 1/6 * max_xyz[i] * (pred_coor_[y][x][i] - 3)
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = -1/6 * max_xyz[i] * (pred_coor_[y][x][i] + 1)
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = 1/6 * max_xyz[i] * (pred_coor_[y][x][i] + 1)
                                elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = -1/6 * max_xyz[i] * (pred_coor_[y][x][i] - 3)
                                elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = 1/6 * max_xyz[i] * (pred_coor_[y][x][i] + 5)
                                else:
                                    unchange += 1
                            if unchange == 0:
                                select_pts_2d.append([w_begin + x * w_unit, h_begin + y * h_unit])
                                select_pts_3d.append(pred_coor_[y][x])

                elif cfg.train.split_num == 7:
                    max_xyz = [max_x, max_y, max_z]
                    pred_conf_xyz1 = np.dstack([pred_conf_x1_, pred_conf_y1_, pred_conf_z1_])
                    pred_conf_xyz2 = np.dstack([pred_conf_x2_, pred_conf_y2_, pred_conf_z2_])
                    pred_conf_xyz3 = np.dstack([pred_conf_x3_, pred_conf_y3_, pred_conf_z3_])
                    low_th = cfg.test.mask_low_th
                    high_th = cfg.test.mask_high_th

                    for x in range(cfg.dataiter.out_res):
                        for y in range(cfg.dataiter.out_res):
                            unchange = 0
                            if pred_conf_[y][x] < cfg.test.mask_threshold:
                                continue
                            for i in range(3):
                                if pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] < low_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = -1/7 * max_xyz[i] * (pred_coor_[y][x][i] + 6)
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] < low_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = 1/7 * max_xyz[i] * (pred_coor_[y][x][i] - 4)
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = -1/7 * max_xyz[i] * (pred_coor_[y][x][i] + 2)
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = 1/7 * max_xyz[i] * (pred_coor_[y][x][i])
                                elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = -1/7 * max_xyz[i] * (pred_coor_[y][x][i] - 2)
                                elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = 1/7 * max_xyz[i] * (pred_coor_[y][x][i] + 4)
                                elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] < low_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = -1/7 * max_xyz[i] * (pred_coor_[y][x][i] - 6)
                                else:
                                    unchange += 1
                            if unchange == 0:
                                select_pts_2d.append([w_begin + x * w_unit, h_begin + y * h_unit])
                                select_pts_3d.append(pred_coor_[y][x])

                elif cfg.train.split_num == 8:
                    max_xyz = [max_x, max_y, max_z]
                    pred_conf_xyz1 = np.dstack([pred_conf_x1_, pred_conf_y1_, pred_conf_z1_])
                    pred_conf_xyz2 = np.dstack([pred_conf_x2_, pred_conf_y2_, pred_conf_z2_])
                    pred_conf_xyz3 = np.dstack([pred_conf_x3_, pred_conf_y3_, pred_conf_z3_])
                    low_th = cfg.test.mask_low_th
                    high_th = cfg.test.mask_high_th

                    for x in range(cfg.dataiter.out_res):
                        for y in range(cfg.dataiter.out_res):
                            unchange = 0
                            if pred_conf_[y][x] < cfg.test.mask_threshold:
                                continue
                            for i in range(3):
                                if pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] < low_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = -0.125 * max_xyz[i] * (pred_coor_[y][x][i] + 7)
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] < low_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = 0.125 * max_xyz[i] * (pred_coor_[y][x][i] - 5)
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = -0.125 * max_xyz[i] * (pred_coor_[y][x][i] + 3)
                                elif pred_conf_xyz1[y][x][i] < low_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = 0.125 * max_xyz[i] * (pred_coor_[y][x][i] - 1)
                                elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = -0.125 * max_xyz[i] * (pred_coor_[y][x][i] - 1)
                                elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] > high_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = 0.125 * max_xyz[i] * (pred_coor_[y][x][i] + 3)
                                elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] < low_th and pred_conf_xyz3[y][x][i] > high_th:
                                    pred_coor_[y][x][i] = -0.125 * max_xyz[i] * (pred_coor_[y][x][i] - 5)
                                elif pred_conf_xyz1[y][x][i] > high_th and pred_conf_xyz2[y][x][i] < low_th and pred_conf_xyz3[y][x][i] < low_th:
                                    pred_coor_[y][x][i] = 0.125 * max_xyz[i] * (pred_coor_[y][x][i] + 7)
                                else:
                                    unchange += 1
                            if unchange == 0:
                                select_pts_2d.append([w_begin + x * w_unit, h_begin + y * h_unit])
                                select_pts_3d.append(pred_coor_[y][x])

                if len(select_pts_2d) < 4:
                    for n in range(4 - len(select_pts_2d)):
                        select_pts_2d.append([0.0, 0.0])
                        select_pts_3d.append([0.0, 0.0, 0.0])
                model_points = np.asarray(select_pts_3d, dtype=np.float64)
                image_points = np.asarray(select_pts_2d, dtype=np.float64)

            try:
                if 'rot' in cfg.pytorch.task.lower():
                    dist_coeffs = np.zeros((4, 1))  # Assuming no lens distortion
                    if cfg.test.pnp == 'iterPnP': # iterative PnP algorithm
                        success, R_vector, T_vector = cv2.solvePnP(model_points, image_points, cfg.dataset.camera_matrix,
                                                                        dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE)
                    elif cfg.test.pnp == 'ransac': # ransac algorithm
                        _, R_vector, T_vector, inliers = cv2.solvePnPRansac(model_points, image_points,
                                                cfg.dataset.camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_EPNP)

                    else:
                        raise NotImplementedError("Not support PnP algorithm: {}".format(cfg.test.pnp))
                    R_matrix = cv2.Rodrigues(R_vector, jacobian=0)[0]
                    pose_est = np.concatenate((R_matrix, np.asarray(T_vector).reshape(3, 1)), axis=1)
                    Eval.pose_est_all[obj_].append(pose_est)
                    Eval.pose_gt_all[obj_].append(pose_gt)
                    Eval.num[obj_] += 1
                    Eval.numAll += 1
            except:
                Eval.num[obj_] += 1
                Eval.numAll += 1
                logger.info('error in solve PnP or Ransac')

            T_end = time.time() - T_begin
            if time_monitor:
                logger.info("time spend on PnP+RANSAC for one image is {}".format(T_end))

        Bar.suffix = 'test Epoch: [{0}][{1}/{2}]| Total: {total:} | ETA: {eta:} | Loss {loss.avg:.4f} | Loss_rot {loss_rot.avg:.4f} | Loss_trans {loss_trans.avg:.4f}'.format(
            epoch, i, num_iters, total=bar.elapsed_td, eta=bar.eta_td, loss=Loss, loss_rot=Loss_rot, loss_trans=Loss_trans)
        bar.next()

    epoch_save_path = os.path.join(cfg.pytorch.save_path, str(epoch))
    if not os.path.exists(epoch_save_path):
        os.makedirs(epoch_save_path)
    if 'rot' in cfg.pytorch.task.lower():
        logger.info("{} Evaluate of Rotation Branch of Epoch {} {}".format('-'*40, epoch, '-'*40))
        preds['poseGT'] = Eval.pose_gt_all
        preds['poseEst'] = Eval.pose_est_all
        if cfg.pytorch.test:
            np.save(os.path.join(epoch_save_path, 'pose_est_all_test.npy'), Eval.pose_est_all)
            np.save(os.path.join(epoch_save_path, 'pose_gt_all_test.npy'), Eval.pose_gt_all)
        else:
            np.save(os.path.join(epoch_save_path, 'pose_est_all_epoch{}.npy'.format(epoch)), Eval.pose_est_all)
            np.save(os.path.join(epoch_save_path, 'pose_gt_all_epoch{}.npy'.format(epoch)), Eval.pose_gt_all)
        # evaluation
        if 'all' in cfg.test.test_mode.lower():
            Eval.evaluate_pose()
            Eval.evaluate_pose_add(epoch_save_path)
            Eval.evaluate_pose_arp_2d(epoch_save_path)
        else:
            if 'pose' in cfg.test.test_mode.lower():
                Eval.evaluate_pose()
            if 'add' in cfg.test.test_mode.lower():
                Eval.evaluate_pose_add(epoch_save_path)
            if 'proj' in cfg.test.test_mode.lower():
                Eval.evaluate_pose_arp_2d(epoch_save_path)

    bar.finish()
    return {'Loss': Loss.avg, 'Loss_rot': Loss_rot.avg, 'Loss_trans': Loss_trans.avg}, preds

